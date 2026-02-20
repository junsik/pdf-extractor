'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  FileText,
  Upload,
  Building2,
  User,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Unlock,
  Loader2,
  Download,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronUp,
  Info,
  LogOut,
  Settings,
  CreditCard,
  Clock,
  Copy,
  Check,
  Code2,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';

interface ParseResult {
  unique_number: string;
  property_type: string;
  property_address: string;
  title_info: any;
  section_a: any[];
  section_b: any[];
  parse_date: string;
}

interface HistoryItem {
  id: number;
  file_name: string;
  status: string;
  unique_number?: string;
  property_address?: string;
  section_a_count: number;
  section_b_count: number;
  created_at: string;
  completed_at?: string;
  processing_time?: number;
}

function formatAmount(amount: number | undefined): string {
  if (!amount) return '-';
  return `${amount.toLocaleString()}원`;
}

export default function DashboardPage() {
  const { user, isLoading: authLoading, logout, refreshUser } = useAuth();
  const router = useRouter();
  
  const [file, setFile] = useState<File | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<{ success: boolean; data?: ParseResult; error?: string; is_demo: boolean; remaining_credits: number } | null>(null);
  const [history, setHistory] = useState<{ items: HistoryItem[]; total: number }>({ items: [], total: 0 });
  const [showRawText, setShowRawText] = useState(false);
  const [jsonCopied, setJsonCopied] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
    }
  }, [user, authLoading, router]);

  useEffect(() => {
    if (user) {
      loadHistory();
    }
  }, [user]);

  const loadHistory = async () => {
    try {
      const data = await api.getParseHistory(1, 10);
      setHistory(data);
    } catch (error) {
      console.error('Failed to load history:', error);
    }
  };

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile && selectedFile.name.toLowerCase().endsWith('.pdf')) {
      setFile(selectedFile);
      setResult(null);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.name.toLowerCase().endsWith('.pdf')) {
      setFile(droppedFile);
      setResult(null);
    }
  }, []);

  const handleParse = useCallback(async () => {
    if (!file) return;

    setIsParsing(true);
    setProgress(0);

    const progressInterval = setInterval(() => {
      setProgress((prev) => (prev >= 90 ? prev : prev + 10));
    }, 200);

    try {
      const response = await api.parsePdf(file, false);
      setProgress(100);
      setResult(response);
      refreshUser();
      loadHistory();
    } catch (error: any) {
      setResult({
        success: false,
        error: error.message || '파싱에 실패했습니다.',
        is_demo: false,
        remaining_credits: user?.credits || 0,
      });
    } finally {
      clearInterval(progressInterval);
      setIsParsing(false);
    }
  }, [file, user?.credits]);

  const handleLogout = () => {
    logout();
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900">
      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm dark:bg-slate-900/80 sticky top-0 z-50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <span className="text-xl font-bold">RegistryParser</span>
          </Link>
          <div className="flex items-center gap-4">
            <Badge variant={user.plan === 'free' ? 'secondary' : 'default'}>
              {user.plan === 'free' ? '무료' : user.plan === 'basic' ? '베이직' : '엔터프라이즈'} 플랜
            </Badge>
            <Link href="/pricing">
              <Button variant="ghost" size="sm">
                <CreditCard className="w-4 h-4 mr-1" />
                요금제
              </Button>
            </Link>
            <Link href="/settings">
              <Button variant="ghost" size="sm">
                <Settings className="w-4 h-4 mr-1" />
                설정
              </Button>
            </Link>
            <Button variant="ghost" size="sm" onClick={handleLogout}>
              <LogOut className="w-4 h-4 mr-1" />
              로그아웃
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid lg:grid-cols-3 gap-6">
          {/* Sidebar */}
          <div className="lg:col-span-1 space-y-4">
            {/* User Info */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-lg flex items-center gap-2">
                  <User className="w-5 h-5" />
                  내 정보
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <p className="text-sm text-muted-foreground">이메일</p>
                  <p className="font-medium">{user.email}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">이름</p>
                  <p className="font-medium">{user.name}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">남은 크레딧</p>
                  <p className="font-medium text-2xl">
                    {user.credits === -1 ? '무제한' : user.credits}회
                  </p>
                </div>
                {user.plan_end_date && (
                  <div>
                    <p className="text-sm text-muted-foreground">플랜 만료일</p>
                    <p className="font-medium">
                      {new Date(user.plan_end_date).toLocaleDateString('ko-KR')}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Upload */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Upload className="w-5 h-5" />
                  PDF 업로드
                </CardTitle>
                <CardDescription>
                  등기부등본 PDF 파일을 업로드하세요. (최대 10MB)
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div
                  className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer
                    ${file ? 'border-green-500 bg-green-50 dark:bg-green-950/20' : 'border-slate-300 hover:border-blue-400'}`}
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  {file ? (
                    <div className="space-y-2">
                      <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto" />
                      <p className="font-medium">{file.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {(file.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <Upload className="w-12 h-12 text-slate-400 mx-auto" />
                      <p className="font-medium">파일을 드래그하거나 클릭하세요</p>
                      <p className="text-sm text-muted-foreground">PDF 파일만 지원됩니다</p>
                    </div>
                  )}
                </div>

                <Button
                  className="w-full"
                  disabled={!file || isParsing}
                  onClick={handleParse}
                >
                  {isParsing ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      파싱 중...
                    </>
                  ) : (
                    <>
                      <FileText className="w-4 h-4 mr-2" />
                      PDF 파싱하기
                    </>
                  )}
                </Button>

                {isParsing && <Progress value={progress} className="h-2" />}
              </CardContent>
            </Card>

            {/* Notice */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Info className="w-4 h-4" />
                  주의사항
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-2">
                <p className="text-muted-foreground">• 디지털 PDF만 지원합니다 (스캔본 미지원)</p>
                <p className="text-muted-foreground">• 건물/집합건물 등기부등본 모두 지원</p>
                <p className="text-muted-foreground">• 말소사항(취소선)도 모두 파싱됩니다</p>
              </CardContent>
            </Card>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-2 space-y-4">
            {/* Result */}
            {result ? (
              result.success && result.data ? (
                <>
                  {result.is_demo && (
                    <Alert className="border-amber-500 bg-amber-50 dark:bg-amber-950/20">
                      <EyeOff className="w-4 h-4 text-amber-500" />
                      <AlertTitle>데모 버전 결과</AlertTitle>
                      <AlertDescription>
                        일부 정보가 마스킹되어 표시됩니다.
                      </AlertDescription>
                    </Alert>
                  )}

                  <Tabs defaultValue="summary" className="w-full">
                    <TabsList className="grid w-full grid-cols-5">
                      <TabsTrigger value="summary">요약</TabsTrigger>
                      <TabsTrigger value="title">표제부</TabsTrigger>
                      <TabsTrigger value="sectionA">갑구</TabsTrigger>
                      <TabsTrigger value="sectionB">을구</TabsTrigger>
                      <TabsTrigger value="json">JSON</TabsTrigger>
                    </TabsList>

                    <TabsContent value="summary" className="space-y-4">
                      <Card>
                        <CardHeader className="pb-3">
                          <CardTitle className="text-lg flex items-center gap-2">
                            <Building2 className="w-5 h-5" />
                            부동산 정보 요약
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="grid sm:grid-cols-2 gap-4">
                            <div>
                              <p className="text-sm text-muted-foreground">고유번호</p>
                              <p className="font-mono font-medium">{result.data.unique_number}</p>
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">부동산 종류</p>
                              <p className="font-medium">
                                {result.data.property_type === 'aggregate_building' ? '집합건물' : '건물'}
                              </p>
                            </div>
                            <div className="sm:col-span-2">
                              <p className="text-sm text-muted-foreground">소재지</p>
                              <p className="font-medium">{result.data.property_address}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="pb-3">
                          <CardTitle className="text-lg">갑구 요약</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>순위</TableHead>
                                <TableHead>등기목적</TableHead>
                                <TableHead>상태</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {result.data.section_a.slice(0, 5).map((entry: any, index: number) => (
                                <TableRow key={index} className={entry.is_cancelled ? 'opacity-50' : ''}>
                                  <TableCell className="font-mono">{entry.rank_number}</TableCell>
                                  <TableCell>{entry.registration_type}</TableCell>
                                  <TableCell>
                                    {entry.is_cancelled ? (
                                      <Badge variant="destructive">말소됨</Badge>
                                    ) : (
                                      <Badge variant="default">유효</Badge>
                                    )}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>

                      <Card>
                        <CardHeader className="pb-3">
                          <CardTitle className="text-lg">을구 요약</CardTitle>
                        </CardHeader>
                        <CardContent>
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>순위</TableHead>
                                <TableHead>등기목적</TableHead>
                                <TableHead>금액</TableHead>
                                <TableHead>상태</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {result.data.section_b.slice(0, 5).map((entry: any, index: number) => (
                                <TableRow key={index} className={entry.is_cancelled ? 'opacity-50' : ''}>
                                  <TableCell className="font-mono">{entry.rank_number}</TableCell>
                                  <TableCell>{entry.registration_type}</TableCell>
                                  <TableCell>
                                    {entry.max_claim_amount && formatAmount(entry.max_claim_amount)}
                                    {entry.deposit_amount && formatAmount(entry.deposit_amount)}
                                  </TableCell>
                                  <TableCell>
                                    {entry.is_cancelled ? (
                                      <Badge variant="destructive">말소됨</Badge>
                                    ) : (
                                      <Badge variant="default">유효</Badge>
                                    )}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </CardContent>
                      </Card>
                    </TabsContent>

                    <TabsContent value="title">
                      <Card>
                        <CardHeader>
                          <CardTitle>표제부 (건물의 표시)</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div className="grid sm:grid-cols-2 gap-4">
                            <div>
                              <p className="text-sm text-muted-foreground">소재지번</p>
                              <p className="font-medium">{result.data.title_info?.address}</p>
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">구조</p>
                              <p className="font-medium">{result.data.title_info?.structure}</p>
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">층수</p>
                              <p className="font-medium">{result.data.title_info?.floors}층</p>
                            </div>
                            <div>
                              <p className="text-sm text-muted-foreground">건물종류</p>
                              <p className="font-medium">{result.data.title_info?.building_type}</p>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    </TabsContent>

                    <TabsContent value="sectionA">
                      <Card>
                        <CardHeader>
                          <CardTitle>갑구 (소유권에 관한 사항)</CardTitle>
                          <CardDescription>총 {result.data.section_a.length}건</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-x-auto">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>순위</TableHead>
                                  <TableHead>등기목적</TableHead>
                                  <TableHead>접수일자</TableHead>
                                  <TableHead>상태</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {result.data.section_a.map((entry: any, index: number) => (
                                  <TableRow key={index} className={entry.is_cancelled ? 'opacity-50 line-through' : ''}>
                                    <TableCell className="font-mono">{entry.rank_number}</TableCell>
                                    <TableCell>{entry.registration_type}</TableCell>
                                    <TableCell className="text-sm">{entry.receipt_date}</TableCell>
                                    <TableCell>
                                      {entry.is_cancelled ? (
                                        <div className="space-y-1">
                                          <Badge variant="destructive">말소됨</Badge>
                                          <p className="text-xs text-muted-foreground">
                                            {entry.cancelled_by_rank}번에서 말소
                                          </p>
                                        </div>
                                      ) : (
                                        <Badge variant="default">유효</Badge>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        </CardContent>
                      </Card>
                    </TabsContent>

                    <TabsContent value="sectionB">
                      <Card>
                        <CardHeader>
                          <CardTitle>을구 (소유권 이외의 권리)</CardTitle>
                          <CardDescription>총 {result.data.section_b.length}건</CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-x-auto">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>순위</TableHead>
                                  <TableHead>등기목적</TableHead>
                                  <TableHead>금액</TableHead>
                                  <TableHead>상태</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {result.data.section_b.map((entry: any, index: number) => (
                                  <TableRow key={index} className={entry.is_cancelled ? 'opacity-50 line-through' : ''}>
                                    <TableCell className="font-mono">{entry.rank_number}</TableCell>
                                    <TableCell>{entry.registration_type}</TableCell>
                                    <TableCell className="text-sm">
                                      {entry.max_claim_amount && (
                                        <span className="text-red-600">{formatAmount(entry.max_claim_amount)}</span>
                                      )}
                                      {entry.deposit_amount && (
                                        <span className="text-blue-600">{formatAmount(entry.deposit_amount)}</span>
                                      )}
                                    </TableCell>
                                    <TableCell>
                                      {entry.is_cancelled ? (
                                        <Badge variant="destructive">말소됨</Badge>
                                      ) : (
                                        <Badge variant="default">유효</Badge>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        </CardContent>
                      </Card>
                    </TabsContent>

                    <TabsContent value="json">
                      <Card>
                        <CardHeader>
                          <div className="flex items-center justify-between">
                            <div>
                              <CardTitle className="flex items-center gap-2">
                                <Code2 className="w-5 h-5" />
                                JSON 원본 데이터
                              </CardTitle>
                              <CardDescription>파싱 결과의 JSON 원본입니다. 복사하여 활용할 수 있습니다.</CardDescription>
                            </div>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                navigator.clipboard.writeText(JSON.stringify(result.data, null, 2));
                                setJsonCopied(true);
                                setTimeout(() => setJsonCopied(false), 2000);
                              }}
                            >
                              {jsonCopied ? (
                                <><Check className="w-4 h-4 mr-1" />복사됨</>
                              ) : (
                                <><Copy className="w-4 h-4 mr-1" />복사</>
                              )}
                            </Button>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <pre className="bg-slate-950 text-slate-50 rounded-lg p-4 overflow-auto max-h-[600px] text-sm font-mono leading-relaxed">
                            {JSON.stringify(result.data, null, 2)}
                          </pre>
                        </CardContent>
                      </Card>
                    </TabsContent>
                  </Tabs>
                </>
              ) : (
                <Card className="border-red-200 bg-red-50 dark:bg-red-950/20">
                  <CardContent className="pt-6">
                    <div className="flex items-center gap-3">
                      <AlertTriangle className="w-8 h-8 text-red-500" />
                      <div>
                        <h3 className="font-medium text-red-700 dark:text-red-400">파싱 실패</h3>
                        <p className="text-sm text-red-600 dark:text-red-300">{result.error}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            ) : (
              <Card className="border-dashed">
                <CardContent className="pt-16 pb-16 text-center">
                  <FileText className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                  <h3 className="text-lg font-medium mb-2">PDF 파일을 업로드하세요</h3>
                  <p className="text-muted-foreground max-w-md mx-auto">
                    등기부등본 PDF 파일을 업로드하고 파싱 버튼을 클릭하면,
                    표제부, 갑구, 을구 정보를 자동으로 추출합니다.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* History */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Clock className="w-5 h-5" />
                    파싱 기록
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    개인정보 보호를 위해 파싱 결과는 서버에 저장되지 않습니다.
                  </p>
                </div>
              </CardHeader>
              <CardContent>
                {history.items.length > 0 ? (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>파일명</TableHead>
                        <TableHead>고유번호</TableHead>
                        <TableHead>상태</TableHead>
                        <TableHead>일시</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {history.items.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell className="font-medium">{item.file_name}</TableCell>
                          <TableCell className="font-mono">{item.unique_number || '-'}</TableCell>
                          <TableCell>
                            <Badge variant={item.status === 'completed' ? 'default' : 'destructive'}>
                              {item.status === 'completed' ? '완료' : '실패'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-sm text-muted-foreground">
                            {new Date(item.created_at).toLocaleString('ko-KR')}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <p className="text-center text-muted-foreground py-8">파싱 기록이 없습니다.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
