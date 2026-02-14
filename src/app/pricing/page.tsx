'use client';

import { useState, useEffect, useRef } from 'react';
import Script from 'next/script';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Check, FileText, Loader2 } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';

interface Plan {
  type: string;
  name: string;
  price: number;
  credits: number;
  features: string[];
}

declare global {
  interface Window {
    TossPayments: (clientKey: string) => {
      payment: (opts: { customerKey: string }) => {
        requestPayment: (opts: any) => Promise<void>;
      };
    };
  }
}

export default function PricingPage() {
  const { user, isAuthenticated } = useAuth();
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [processingPlan, setProcessingPlan] = useState<string | null>(null);
  const [tossReady, setTossReady] = useState(false);
  const clientKeyRef = useRef<string | null>(null);

  useEffect(() => {
    loadPricing();
    loadTossClientKey();
  }, []);

  const loadPricing = async () => {
    try {
      const data = await api.getPricing();
      setPlans(data.plans);
    } catch (error) {
      console.error('Failed to load pricing:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadTossClientKey = async () => {
    try {
      const data = await api.getTossClientKey();
      clientKeyRef.current = data.client_key;
    } catch (error) {
      console.error('Failed to load Toss client key:', error);
    }
  };

  const handleSelectPlan = async (planType: string) => {
    if (!isAuthenticated) {
      router.push('/signup');
      return;
    }

    if (planType === 'free') {
      router.push('/dashboard');
      return;
    }

    if (user?.plan === planType) return;

    if (!tossReady || !clientKeyRef.current) {
      alert('결제 시스템을 불러오는 중입니다. 잠시 후 다시 시도해주세요.');
      return;
    }

    setProcessingPlan(planType);
    try {
      const currentUrl = window.location.origin;
      const order = await api.createPayment({
        plan_type: planType,
        success_url: `${currentUrl}/payment/success`,
        fail_url: `${currentUrl}/payment/fail`,
      });

      const tossPayments = window.TossPayments(clientKeyRef.current);
      const payment = tossPayments.payment({
        customerKey: `user_${user?.id}`,
      });

      await payment.requestPayment({
        method: 'CARD',
        amount: {
          currency: 'KRW',
          value: order.amount,
        },
        orderId: order.order_id,
        orderName: order.order_name,
        successUrl: `${currentUrl}/payment/success`,
        failUrl: `${currentUrl}/payment/fail`,
        customerEmail: order.customer_email,
        customerName: order.customer_name,
      });
    } catch (error: any) {
      // 사용자가 결제창을 닫은 경우
      if (error?.code === 'USER_CANCEL' || error?.code === 'PAY_PROCESS_CANCELED') {
        console.log('결제 취소');
      } else {
        console.error('결제 실패:', error);
        alert(error instanceof Error ? error.message : '결제 처리 중 오류가 발생했습니다.');
      }
    } finally {
      setProcessingPlan(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900">
      {/* Toss Payments SDK v2 */}
      <Script
        src="https://js.tosspayments.com/v2/standard"
        onLoad={() => setTossReady(true)}
      />

      {/* Header */}
      <header className="border-b bg-white/80 backdrop-blur-sm dark:bg-slate-900/80">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <span className="text-xl font-bold">RegistryParser</span>
          </Link>
          <div className="flex items-center gap-4">
            {isAuthenticated ? (
              <>
                <Badge variant={user?.plan === 'free' ? 'secondary' : 'default'}>
                  {user?.plan === 'free' ? '무료' : user?.plan === 'basic' ? '베이직' : '프로'} 플랜
                </Badge>
                <Link href="/dashboard">
                  <Button variant="ghost">대시보드</Button>
                </Link>
              </>
            ) : (
              <>
                <Link href="/login">
                  <Button variant="ghost">로그인</Button>
                </Link>
                <Link href="/signup">
                  <Button>무료로 시작</Button>
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-20">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-4">요금제</h1>
          <p className="text-xl text-muted-foreground">
            필요에 맞는 플랜을 선택하세요
          </p>
        </div>

        {isLoading ? (
          <div className="flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {plans.map((plan, index) => (
              <Card
                key={index}
                className={`relative ${plan.type === 'basic' ? 'border-blue-600 shadow-lg' : ''}`}
              >
                {plan.type === 'basic' && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge>인기</Badge>
                  </div>
                )}
                <CardHeader className="text-center">
                  <CardTitle className="text-2xl">{plan.name}</CardTitle>
                  <div className="mt-4">
                    <span className="text-5xl font-bold">
                      {plan.price === 0 ? '무료' : plan.price.toLocaleString() + '원'}
                    </span>
                    {plan.price > 0 && (
                      <span className="text-muted-foreground">/월</span>
                    )}
                  </div>
                  <p className="text-muted-foreground mt-2">
                    월 {plan.credits === -1 ? '무제한' : plan.credits + '회'} 파싱
                  </p>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-3">
                    {plan.features.map((feature, i) => (
                      <li key={i} className="flex items-center gap-2">
                        <Check className="w-5 h-5 text-green-500 shrink-0" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </CardContent>
                <CardFooter>
                  <Button
                    className="w-full"
                    variant={plan.type === 'basic' ? 'default' : 'outline'}
                    onClick={() => handleSelectPlan(plan.type)}
                    disabled={processingPlan !== null || (isAuthenticated && user?.plan === plan.type)}
                  >
                    {processingPlan === plan.type ? (
                      <><Loader2 className="w-4 h-4 mr-2 animate-spin" />결제 처리 중...</>
                    ) : isAuthenticated && user?.plan === plan.type ? (
                      '현재 플랜'
                    ) : (
                      '시작하기'
                    )}
                  </Button>
                </CardFooter>
              </Card>
            ))}
          </div>
        )}

        {/* Feature Comparison */}
        <div className="mt-20 max-w-4xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-8">기능 비교</h2>
          <Card>
            <CardContent className="p-0">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left p-4">기능</th>
                    <th className="text-center p-4">무료</th>
                    <th className="text-center p-4 bg-blue-50 dark:bg-blue-950/20">베이직</th>
                    <th className="text-center p-4">프로</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { feature: 'PDF 파싱', free: '3회', basic: '10회', pro: '무제한' },
                    { feature: '상세 결과', free: '❌', basic: '✅', pro: '✅' },
                    { feature: '말소사항 추적', free: '✅', basic: '✅', pro: '✅' },
                    { feature: 'Webhook 연동', free: '❌', basic: '✅', pro: '✅' },
                    { feature: 'API 액세스', free: '❌', basic: '✅', pro: '✅' },
                    { feature: '우선 처리', free: '❌', basic: '❌', pro: '✅' },
                    { feature: '전담 지원', free: '❌', basic: '❌', pro: '✅' },
                  ].map((row, index) => (
                    <tr key={index} className="border-b last:border-0">
                      <td className="p-4 font-medium">{row.feature}</td>
                      <td className="text-center p-4">{row.free}</td>
                      <td className="text-center p-4 bg-blue-50 dark:bg-blue-950/20">{row.basic}</td>
                      <td className="text-center p-4">{row.pro}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>

        {/* FAQ */}
        <div className="mt-20 max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-8">자주 묻는 질문</h2>
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">플랜을 언제든 변경할 수 있나요?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  네, 언제든지 플랜을 업그레이드하거나 다운그레이드할 수 있습니다.
                  업그레이드 시 즉시 적용되며, 다운그레이드 시 현재 결제 기간이 끝난 후 적용됩니다.
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">크레딧은 어떻게 계산되나요?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  PDF 파일 1개를 파싱할 때마다 1크레딧이 차감됩니다.
                  프로 플랜은 무제한으로 사용할 수 있습니다.
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">결제 수단은 무엇인가요?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  Toss Payments를 통해 신용카드, 계좌이체, 가상계좌 등 다양한 결제 수단을 지원합니다.
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">파싱 결과는 저장되나요?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  등기부등본에는 주민등록번호, 소유자 정보 등 민감한 개인정보가 포함되어 있어
                  파싱 결과는 서버에 저장하지 않습니다. 결과는 요청 시 즉시 반환되며,
                  이후 다시 확인이 필요한 경우 PDF를 재업로드해주세요.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
