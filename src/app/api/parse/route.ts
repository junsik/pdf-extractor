import { NextRequest, NextResponse } from 'next/server';
import { parseAndProcessPDF, parseRegistryPDF, maskForDemo } from '@/lib/pdf-parser';

export const runtime = 'nodejs';
export const maxDuration = 60; // 최대 60초

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('file') as File;
    const isPaid = formData.get('isPaid') === 'true';
    const webhookUrl = formData.get('webhookUrl') as string | null;

    if (!file) {
      return NextResponse.json(
        { success: false, error: 'PDF 파일이 필요합니다.' },
        { status: 400 }
      );
    }

    // 파일 확장자 확인
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      return NextResponse.json(
        { success: false, error: 'PDF 파일만 업로드 가능합니다.' },
        { status: 400 }
      );
    }

    // 파일 크기 확인 (최대 10MB)
    if (file.size > 10 * 1024 * 1024) {
      return NextResponse.json(
        { success: false, error: '파일 크기는 10MB 이하여야 합니다.' },
        { status: 400 }
      );
    }

    // 파일 버퍼로 변환
    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // PDF 파싱 실행
    const result = await parseAndProcessPDF(
      buffer,
      isPaid,
      webhookUrl || undefined
    );

    return NextResponse.json(result);
  } catch (error) {
    console.error('PDF 파싱 API 오류:', error);
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : '서버 오류가 발생했습니다.',
        requestId: crypto.randomUUID(),
        isDemo: true,
      },
      { status: 500 }
    );
  }
}

// 데모 파싱 (무료)
export async function PUT(request: NextRequest) {
  try {
    const formData = await request.formData();
    const file = formData.get('file') as File;

    if (!file) {
      return NextResponse.json(
        { success: false, error: 'PDF 파일이 필요합니다.' },
        { status: 400 }
      );
    }

    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    // 데모 버전으로 파싱
    const result = await parseAndProcessPDF(buffer, false);

    return NextResponse.json(result);
  } catch (error) {
    console.error('데모 파싱 API 오류:', error);
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : '서버 오류가 발생했습니다.',
        requestId: crypto.randomUUID(),
        isDemo: true,
      },
      { status: 500 }
    );
  }
}
