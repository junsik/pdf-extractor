import { v4 as uuidv4 } from 'uuid';
import {
  RegistryData,
  RegistryTitleInfo,
  SectionAEntry,
  SectionBEntry,
  FloorArea,
  OwnerInfo,
  CreditorInfo,
  ParseResponse,
  WebhookPayload,
  LesseeInfo,
} from '@/types/registry';

// 금액 문자열을 숫자로 변환
function parseAmount(text: string): number | undefined {
  if (!text) return undefined;
  const match = text.match(/금\s*([\d,]+)\s*원/);
  if (match) {
    return parseInt(match[1].replace(/,/g, ''), 10);
  }
  return undefined;
}

// 면적 문자열에서 숫자 추출
function parseArea(text: string): number | undefined {
  const match = text.match(/([\d,.]+)\s*㎡/);
  if (match) {
    return parseFloat(match[1].replace(/,/g, ''));
  }
  return undefined;
}

// 층별 면적 파싱
function parseFloorAreas(text: string): FloorArea[] {
  const areas: FloorArea[] = [];
  const lines = text.split('\n');
  
  for (const line of lines) {
    const match = line.match(/(지하?\d+층|\d+층|옥탑\d+층)\s*([\d,.]+)\s*㎡/);
    if (match) {
      const isExcluded = line.includes('연면적제외');
      areas.push({
        floor: match[1],
        area: parseFloat(match[2].replace(/,/g, '')),
        isExcluded,
      });
    }
  }
  
  return areas;
}

// 고유번호 추출
function extractUniqueNumber(text: string): string {
  const match = text.match(/고유번호\s*([\d-]+)/);
  return match ? match[1] : '';
}

// 부동산 종류 판별
function detectPropertyType(text: string): 'building' | 'aggregate_building' {
  if (text.includes('집합건물')) {
    return 'aggregate_building';
  }
  return 'building';
}

// 주소 추출
function extractAddress(text: string): string {
  // [건물] 또는 [집합건물] 다음에 오는 주소
  const match = text.match(/\[(?:건물|집합건물)\]\s*(.+?)(?:\n|【)/);
  return match ? match[1].trim() : '';
}

// 표제부 파싱
function parseTitleSection(text: string): RegistryTitleInfo {
  const uniqueNumber = extractUniqueNumber(text);
  const propertyType = detectPropertyType(text);
  
  // 소재지번 추출
  const addressMatch = text.match(/소재지번[,\s]*건물명칭 및 번호.*?\n.*?\n?\s*([^\n]+)/s);
  const address = addressMatch ? addressMatch[1].trim() : '';
  
  // 도로명주소 추출
  const roadAddressMatch = text.match(/\[도로명주소\]\s*\n?\s*([^\n]+)/);
  const roadAddress = roadAddressMatch ? roadAddressMatch[1].trim() : undefined;
  
  // 구조 추출
  const structureMatch = text.match(/(철근콘크리트구조|철골철근콘크리트구조|목구조|벽돌구조|블록구조|경량철골구조)/);
  const structure = structureMatch ? structureMatch[1] : '';
  
  // 지붕 추출
  const roofMatch = text.match(/\(철근\)?콘크리트\s*지붕|\(기와\)\s*지붕|\(슬레이트\)\s*지붕/);
  const roofType = roofMatch ? roofMatch[0] : '';
  
  // 층수 추출
  const floorsMatch = text.match(/(\d+)층/);
  const floors = floorsMatch ? parseInt(floorsMatch[1], 10) : 0;
  
  // 건물종류 추출
  const typeMatch = text.match(/(아파트|오피스텔|다세대주택|다가구주택|단독주택|근린생활시설|제2종근린생활시설|상가|업무시설|주택)/);
  const buildingType = typeMatch ? typeMatch[1] : '';
  
  // 층별 면적 파싱
  const areas = parseFloorAreas(text);
  
  // 집합건물인 경우 대지권 및 전유부분 파싱
  let landRightRatio: string | undefined;
  let exclusiveArea: number | undefined;
  
  if (propertyType === 'aggregate_building') {
    const ratioMatch = text.match(/대지권비율\s*\n?\s*(\d+)분의\s*([\d.]+)/);
    if (ratioMatch) {
      landRightRatio = `${ratioMatch[1]}분의 ${ratioMatch[2]}`;
    }
    
    const exclusiveMatch = text.match(/전유부분.*?건물의 표시.*?([\d,.]+)\s*㎡/s);
    if (exclusiveMatch) {
      exclusiveArea = parseFloat(exclusiveMatch[1].replace(/,/g, ''));
    }
  }
  
  return {
    uniqueNumber,
    propertyType,
    address,
    roadAddress,
    structure,
    roofType,
    floors,
    buildingType,
    areas,
    landRightRatio,
    exclusiveArea,
  };
}

// 갑구 엔트리 파싱
function parseSectionAEntries(text: string): SectionAEntry[] {
  const entries: SectionAEntry[] = [];
  
  // 갑구 섹션 찾기
  const sectionAMatch = text.match(/【\s*갑\s*구\s*】.*?(?=【\s*을\s*구\s*】|【\s*매\s*매\s*목\s*록\s*】|$)/s);
  if (!sectionAMatch) return entries;
  
  const sectionAText = sectionAMatch[0];
  
  // 테이블 행 패턴으로 파싱
  // 순위번호 | 등기목적 | 접수 | 등기원인 | 권리자 및 기타사항
  const rowPattern = /(\d+(?:-\d+)?)\s+(소유권보존|소유권이전|가압류|압류|경매개시결정|임의경매개시결정|강제경매개시결정|가처분|등기말소|소유권이전등기말소)[\s\S]*?(?=\n\d+(?:-\d+)?\s+|\n【|\n\s*$)/g;
  
  let match;
  while ((match = rowPattern.exec(sectionAText)) !== null) {
    const fullMatch = match[0];
    const rankNumber = match[1];
    const registrationType = match[2];
    
    // 접수일자와 접수번호 추출
    const receiptMatch = fullMatch.match(/(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s*제?\s*([\d]+호)/);
    const receiptDate = receiptMatch ? receiptMatch[1] : '';
    const receiptNumber = receiptMatch ? receiptMatch[2] : '';
    
    // 등기원인 추출
    const causeMatch = fullMatch.match(/등\s*기\s*원\s*인\s*\n?\s*([\s\S]*?)(?=권리자|소유자|채권자|$)/);
    const registrationCause = causeMatch ? causeMatch[1].trim() : '';
    
    // 등기원인일자 추출
    const causeDateMatch = fullMatch.match(/(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s*(?:매매|상속|증여|신탁|경락)/);
    const registrationCauseDate = causeDateMatch ? causeDateMatch[1] : undefined;
    
    // 소유자 정보 추출
    const ownerMatch = fullMatch.match(/소유자\s+([^\d]+)\s+(\d{6}-\*{7})?\s*\n?\s*([^\n]*)/);
    let owner: OwnerInfo | undefined;
    if (ownerMatch) {
      owner = {
        name: ownerMatch[1].trim(),
        residentNumber: ownerMatch[2],
        address: ownerMatch[3]?.trim(),
      };
    }
    
    // 채권자 정보 추출 (가압류, 경매 등)
    const creditorMatch = fullMatch.match(/채권자\s+([^\d]+)\s+(\d{6}-\*{7}|\d{3}-\d{2}-\d{5})?\s*\n?\s*([^\n]*)/);
    let creditor: CreditorInfo | undefined;
    if (creditorMatch) {
      creditor = {
        name: creditorMatch[1].trim(),
        residentNumber: creditorMatch[2],
        address: creditorMatch[3]?.trim(),
      };
    }
    
    // 청구금액 추출
    const claimAmount = parseAmount(fullMatch.match(/청구금액\s*(금[\d,]+원)/)?.[1] || '');
    
    // 말소 여부 확인
    const isCancelled = fullMatch.includes('말소');
    const cancellationInfo = isCancelled ? fullMatch.match(/(\d+번[^\n]*말소)/)?.[1] : undefined;
    
    entries.push({
      rankNumber,
      registrationType,
      receiptDate,
      receiptNumber,
      registrationCause,
      registrationCauseDate,
      owner,
      creditor,
      claimAmount,
      isCancelled,
      cancellationInfo,
    });
  }
  
  return entries;
}

// 을구 엔트리 파싱
function parseSectionBEntries(text: string): SectionBEntry[] {
  const entries: SectionBEntry[] = [];
  
  // 을구 섹션 찾기
  const sectionBMatch = text.match(/【\s*을\s*구\s*】[\s\S]*?(?=【\s*매\s*매\s*목\s*록\s*】|주요\s*등기사항\s*요약|출력일시|$)/);
  if (!sectionBMatch) return entries;
  
  const sectionBText = sectionBMatch[0];
  
  // 근저당권, 임차권, 전세권 등 패턴
  const rowPattern = /(\d+(?:-\d+)?)\s+(근저당권설정|근저당권이전|근질권설정|주택임차권|전세권설정|저당권설정|임차권설정)[\s\S]*?(?=\n\d+(?:-\d+)?\s+|\n【|\n출력일시|\n주요\s*등기|$)/g;
  
  let match;
  while ((match = rowPattern.exec(sectionBText)) !== null) {
    const fullMatch = match[0];
    const rankNumber = match[1];
    const registrationType = match[2];
    
    // 접수일자와 접수번호 추출
    const receiptMatch = fullMatch.match(/(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s*제?\s*([\d]+호)/);
    const receiptDate = receiptMatch ? receiptMatch[1] : '';
    const receiptNumber = receiptMatch ? receiptMatch[2] : '';
    
    // 등기원인 추출
    const causeMatch = fullMatch.match(/등\s*기\s*원\s*인\s*\n?\s*([\s\S]*?)(?=채권|채무|근저|임차|$)/);
    const registrationCause = causeMatch ? causeMatch[1].trim() : '';
    
    const causeDateMatch = fullMatch.match(/(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s*(?:설정계약|추가설정계약|확정채권양도|계약인수)/);
    const registrationCauseDate = causeDateMatch ? causeDateMatch[1] : undefined;
    
    // 채권최고액 추출
    const maxClaimAmount = parseAmount(fullMatch.match(/채권최고액\s*(금[\d,]+원)/)?.[1] || '');
    
    // 채무자 정보
    const debtorMatch = fullMatch.match(/채무자\s+([^\d\n]+)\s+(\d{6}-\*{7}|\d{3}-\d{2}-\d{5})?\s*\n?\s*([^\n채근]*)/);
    let debtor: OwnerInfo | undefined;
    if (debtorMatch) {
      debtor = {
        name: debtorMatch[1].trim(),
        residentNumber: debtorMatch[2],
        address: debtorMatch[3]?.trim(),
      };
    }
    
    // 근저당권자 정보
    const mortgageeMatch = fullMatch.match(/근저당권자\s+([^\d\n]+)\s+(\d{3}-\d{2}-\d{5}|\d{6}-\*{7})?\s*\n?\s*([^\n임채공]*)/);
    let mortgagee: CreditorInfo | undefined;
    if (mortgageeMatch) {
      mortgagee = {
        name: mortgageeMatch[1].trim(),
        residentNumber: mortgageeMatch[2],
        address: mortgageeMatch[3]?.trim(),
      };
    }
    
    // 임차보증금 추출
    const depositAmount = parseAmount(fullMatch.match(/임차보증금\s*(금[\d,]+원)/)?.[1] || '');
    
    // 차임(월세) 추출
    const monthlyRent = parseAmount(fullMatch.match(/차\s*임\s*월?\s*금?\s*(금[\d,]+원)/)?.[1] || '');
    
    // 임대차 정보 추출
    const contractDateMatch = fullMatch.match(/임대차계약일자\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)/);
    const residentRegMatch = fullMatch.match(/주민등록일자\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)/);
    const possessionMatch = fullMatch.match(/점유개시일자\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)/);
    const fixedDateMatch = fullMatch.match(/확정일자\s*(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)/);
    
    const leaseTerm = contractDateMatch ? {
      contractDate: contractDateMatch[1],
      residentRegistrationDate: residentRegMatch?.[1],
      possessionStartDate: possessionMatch?.[1],
      fixedDate: fixedDateMatch?.[1],
    } : undefined;
    
    // 임차권자 정보
    const lesseeMatch = fullMatch.match(/임차권자\s+([^\d\n]+)\s+(\d{6}-\*{7})?\s*\n?\s*([^\n]*)/);
    let lessee: LesseeInfo | undefined;
    if (lesseeMatch) {
      lessee = {
        name: lesseeMatch[1].trim(),
        residentNumber: lesseeMatch[2],
        address: lesseeMatch[3]?.trim(),
      };
    }
    
    // 임차 범위 추출
    const areaMatch = fullMatch.match(/범\s*위\s*([\s\S]*?)(?=임대차계약일자|$)/);
    const leaseArea = areaMatch ? areaMatch[1].trim().substring(0, 200) : undefined;
    
    // 말소 여부
    const isCancelled = fullMatch.includes('말소');
    
    entries.push({
      rankNumber,
      registrationType,
      receiptDate,
      receiptNumber,
      registrationCause,
      registrationCauseDate,
      maxClaimAmount,
      debtor,
      mortgagee,
      depositAmount,
      monthlyRent,
      leaseTerm,
      lessee,
      leaseArea,
      isCancelled,
    });
  }
  
  return entries;
}

// 등기부등본 전체 파싱
export async function parseRegistryPDF(pdfBuffer: Buffer): Promise<RegistryData> {
  // PDF 텍스트 추출
  let text = '';
  
  try {
    // pdf2json 사용
    const PDFParser = (await import('pdf2json')).default;
    const pdfParser = new (PDFParser as any)(null, 1);
    
    const parsePromise = new Promise<string>((resolve, reject) => {
      pdfParser.on('pdfParser_dataError', (errData: any) => {
        reject(new Error(errData.parserError));
      });
      
      pdfParser.on('pdfParser_dataReady', (pdfData: any) => {
        const texts: string[] = [];
        for (const page of pdfData.Pages || []) {
          for (const item of page.Texts || []) {
            for (const t of item.R || []) {
              texts.push(decodeURIComponent(t.T || ''));
            }
            texts.push('\n');
          }
          texts.push('\n--- PAGE BREAK ---\n');
        }
        resolve(texts.join(''));
      });
    });
    
    pdfParser.parseBuffer(pdfBuffer);
    text = await parsePromise;
  } catch (error) {
    console.error('pdf2json 파싱 오류, 대체 방식 사용:', error);
    // 대체: pdf-parse 시도
    try {
      const pdfParse = await import('pdf-parse');
      const parseFn = 'default' in pdfParse ? pdfParse.default : pdfParse;
      const data = await parseFn(pdfBuffer);
      text = data.text;
    } catch (e) {
      console.error('pdf-parse도 실패:', e);
      throw new Error('PDF 텍스트 추출에 실패했습니다.');
    }
  }
  
  // 고유번호
  const uniqueNumber = extractUniqueNumber(text);
  
  // 부동산 종류
  const propertyType = detectPropertyType(text);
  
  // 부동산 주소
  const propertyAddress = extractAddress(text);
  
  // 표제부 파싱
  const titleInfo = parseTitleSection(text);
  
  // 갑구 파싱
  const sectionA = parseSectionAEntries(text);
  
  // 을구 파싱
  const sectionB = parseSectionBEntries(text);
  
  return {
    uniqueNumber,
    propertyType,
    propertyAddress,
    titleInfo,
    sectionA,
    sectionB,
    rawText: text,
    parseDate: new Date().toISOString(),
  };
}

// 데모 버전용 데이터 마스킹
export function maskForDemo(data: RegistryData): Partial<RegistryData> {
  return {
    uniqueNumber: data.uniqueNumber,
    propertyType: data.propertyType,
    propertyAddress: data.propertyAddress,
    titleInfo: {
      ...data.titleInfo,
      // 층별 면적은 첫 번째 층만 표시
      areas: data.titleInfo.areas.slice(0, 1),
    },
    sectionA: data.sectionA.slice(0, 1).map(entry => ({
      ...entry,
      owners: (entry.owners ?? []).map(o => ({
        ...o,
        name: o.name.charAt(0) + '*' + o.name.slice(-1),
        residentNumber: o.residentNumber ? '******-*******' : undefined,
        address: o.address ? o.address.substring(0, 10) + '...' : undefined,
      })),
    })),
    sectionB: data.sectionB.slice(0, 1).map(entry => ({
      rankNumber: entry.rankNumber,
      registrationType: entry.registrationType,
      receiptDate: entry.receiptDate,
      // 금액은 마스킹
      maxClaimAmount: undefined,
      depositAmount: undefined,
      // 상세 정보는 숨김
      mortgagee: undefined,
      lessee: undefined,
      leaseTerm: undefined,
    })),
    parseDate: data.parseDate,
  };
}

// Webhook 발송
export async function sendWebhook(
  webhookUrl: string,
  requestId: string,
  data: RegistryData | Partial<RegistryData>,
  isSuccess: boolean,
  secretKey: string = 'default-secret-key'
): Promise<boolean> {
  try {
    const timestamp = new Date().toISOString();
    
    // HMAC 서명 생성 (간단한 구현)
    const signaturePayload = `${requestId}:${timestamp}:${isSuccess}`;
    const signature = Buffer.from(signaturePayload).toString('base64');
    
    const payload: WebhookPayload = {
      event: isSuccess ? 'parsing.completed' : 'parsing.failed',
      timestamp,
      data: {
        requestId,
        status: isSuccess ? 'success' : 'failed',
        downloadUrl: isSuccess ? `/api/download/${requestId}` : undefined,
        summary: isSuccess ? data : undefined,
        error: isSuccess ? undefined : 'Parsing failed',
      },
      signature,
    };
    
    const response = await fetch(webhookUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Signature': signature,
      },
      body: JSON.stringify(payload),
    });
    
    return response.ok;
  } catch (error) {
    console.error('Webhook 전송 실패:', error);
    return false;
  }
}

// 메인 파싱 함수 (데모/유료 분기 처리)
export async function parseAndProcessPDF(
  pdfBuffer: Buffer,
  isPaid: boolean,
  webhookUrl?: string
): Promise<ParseResponse> {
  const requestId = uuidv4();
  
  try {
    // PDF 파싱
    const fullData = await parseRegistryPDF(pdfBuffer);
    
    // Webhook 발송 (설정된 경우)
    if (webhookUrl) {
      await sendWebhook(
        webhookUrl,
        requestId,
        isPaid ? fullData : maskForDemo(fullData),
        true
      );
    }
    
    return {
      success: true,
      data: isPaid ? fullData : undefined,
      requestId,
      isDemo: !isPaid,
      // 데모 버전은 마스킹된 데이터 반환
      ...(isPaid ? {} : { data: maskForDemo(fullData) as RegistryData }),
    };
  } catch (error) {
    console.error('PDF 파싱 오류:', error);
    
    // 실패 시에도 Webhook 발송
    if (webhookUrl) {
      await sendWebhook(webhookUrl, requestId, {}, false);
    }
    
    return {
      success: false,
      error: error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.',
      requestId,
      isDemo: !isPaid,
    };
  }
}
