'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  FileText,
  Upload,
  Search,
  Shield,
  Zap,
  Globe,
  Check,
  ArrowRight,
  Building2,
  CreditCard,
  Clock,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';

const features = [
  {
    icon: FileText,
    title: '자동 PDF 파싱',
    description: '등기부등본 PDF를 업로드하면 표제부, 갑구, 을구를 자동으로 분석합니다.',
  },
  {
    icon: Search,
    title: '말소사항 추적',
    description: '취소선으로 표시된 말소 항목까지 완벽하게 추적하여 현재 유효한 권리 관계를 파악합니다.',
  },
  {
    icon: Globe,
    title: 'Webhook 연동',
    description: '파싱 완료 시 지정된 URL로 결과를 전송하여 시스템 통합이 간편합니다.',
  },
  {
    icon: Zap,
    title: '빠른 처리',
    description: '평균 3초 이내 파싱 완료. 대량 처리도 지원합니다.',
  },
  {
    icon: Shield,
    title: '보안 강화',
    description: '개인정보는 암호화하여 저장하며, 데모 버전에서는 마스킹 처리됩니다.',
  },
  {
    icon: CreditCard,
    title: '간편 결제',
    description: 'Toss Payments 연동으로 안전하고 간편한 결제를 지원합니다.',
  },
];

const plans = [
  {
    name: '무료',
    price: '0원',
    period: '월',
    credits: '10회',
    features: ['월 10회 파싱', '기본 결과', '말소사항 추적'],
    cta: '시작하기',
    popular: false,
  },
  {
    name: '베이직',
    price: '9,900원',
    period: '월',
    credits: '100회',
    features: ['월 100회 파싱', '상세 결과', 'Webhook 지원', 'API 액세스'],
    cta: '시작하기',
    popular: true,
  },
  {
    name: '엔터프라이즈',
    price: '별도 문의',
    period: '',
    credits: '맞춤',
    features: ['맞춤 파싱 한도', '우선 처리', 'Webhook 지원', 'API 액세스', '전담 지원'],
    cta: '문의하기',
    popular: false,
  },
];

const faqs = [
  {
    question: '어떤 종류의 등기부등본을 지원하나요?',
    answer: '건물 등기부등본과 집합건물(아파트, 오피스텔 등) 등기부등본을 모두 지원합니다. 단, 디지털 PDF(텍스트 기반)만 지원하며 스캔본(이미지)은 지원하지 않습니다.',
  },
  {
    question: '말소사항도 파싱되나요?',
    answer: '네, 등기부등본에서 실선으로 그어진 말소 항목도 모두 파싱됩니다. 원본 등기와 말소 등기를 자동으로 매핑하여 현재 유효한 권리 관계를 쉽게 파악할 수 있습니다.',
  },
  {
    question: '파싱 결과는 어떻게 확인하나요?',
    answer: '웹 대시보드에서 바로 확인하거나, Webhook을 통해 지정된 URL로 결과를 받을 수 있습니다. API를 통한 프로그래밍 방식 접근도 가능합니다.',
  },
  {
    question: '개인정보는 안전한가요?',
    answer: '모든 개인정보는 암호화하여 저장되며, 데모 버전에서는 자동으로 마스킹 처리됩니다. 데이터 보관 기간이 지나면 자동 삭제됩니다.',
  },
];

export default function HomePage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push('/dashboard');
    }
  }, [isAuthenticated, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b bg-white/80 backdrop-blur-sm dark:bg-slate-900/80">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <span className="text-xl font-bold">RegistryParser</span>
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/pricing">
              <Button variant="ghost">요금제</Button>
            </Link>
            <Link href="/login">
              <Button variant="ghost">로그인</Button>
            </Link>
            <Link href="/signup">
              <Button>무료로 시작</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="container mx-auto px-4 py-20 text-center">
        <Badge variant="secondary" className="mb-6">
          🚀 빠르고 정확한 등기부등본 파싱
        </Badge>
        <h1 className="text-4xl md:text-6xl font-bold mb-6 bg-gradient-to-r from-blue-600 to-cyan-600 bg-clip-text text-transparent">
          등기부등본 PDF를
          <br />
          스마트하게 분석하세요
        </h1>
        <p className="text-xl text-muted-foreground mb-8 max-w-2xl mx-auto">
          PDF 업로드만으로 표제부, 갑구, 을구를 자동 분석.
          <br />
          말소사항까지 완벽하게 추적합니다.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link href="/signup">
            <Button size="lg" className="gap-2">
              무료로 시작하기 <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
          <Link href="/pricing">
            <Button size="lg" variant="outline">
              요금제 보기
            </Button>
          </Link>
        </div>
      </section>

      {/* Demo Preview */}
      <section className="container mx-auto px-4 py-12">
        <div className="bg-slate-900 rounded-2xl p-8 text-white">
          <div className="grid md:grid-cols-3 gap-6">
            <div className="text-center">
              <Building2 className="w-12 h-12 mx-auto mb-4 text-blue-400" />
              <h3 className="font-semibold mb-2">표제부</h3>
              <p className="text-sm text-slate-400">
                건물 정보, 층별 면적, 대지권 등
              </p>
            </div>
            <div className="text-center">
              <Shield className="w-12 h-12 mx-auto mb-4 text-green-400" />
              <h3 className="font-semibold mb-2">갑구</h3>
              <p className="text-sm text-slate-400">
                소유권 변동, 경매, 압류 현황
              </p>
            </div>
            <div className="text-center">
              <CreditCard className="w-12 h-12 mx-auto mb-4 text-purple-400" />
              <h3 className="font-semibold mb-2">을구</h3>
              <p className="text-sm text-slate-400">
                근저당권, 임차권, 전세권 등
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="container mx-auto px-4 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold mb-4">강력한 기능</h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            등기부등본 분석에 필요한 모든 기능을 제공합니다.
          </p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((feature, index) => (
            <Card key={index}>
              <CardHeader>
                <feature.icon className="w-10 h-10 text-blue-600 mb-2" />
                <CardTitle className="text-lg">{feature.title}</CardTitle>
              </CardHeader>
              <CardContent>
                <CardDescription>{feature.description}</CardDescription>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Pricing */}
      <section className="container mx-auto px-4 py-20 bg-slate-50 dark:bg-slate-900/50 rounded-3xl">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold mb-4">요금제</h2>
          <p className="text-muted-foreground">필요에 맞는 플랜을 선택하세요.</p>
        </div>
        <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
          {plans.map((plan, index) => (
            <Card
              key={index}
              className={`relative ${plan.popular ? 'border-blue-600 shadow-lg' : ''}`}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <Badge>인기</Badge>
                </div>
              )}
              <CardHeader className="text-center">
                <CardTitle>{plan.name}</CardTitle>
                <div className="mt-4">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-muted-foreground">/{plan.period}</span>
                </div>
                <p className="text-sm text-muted-foreground mt-2">
                  월 {plan.credits} 파싱
                </p>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {plan.features.map((feature, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <Check className="w-4 h-4 text-green-500" />
                      <span className="text-sm">{feature}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
              <CardFooter>
                <Link href="/signup" className="w-full">
                  <Button className="w-full" variant={plan.popular ? 'default' : 'outline'}>
                    {plan.cta}
                  </Button>
                </Link>
              </CardFooter>
            </Card>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section className="container mx-auto px-4 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold mb-4">자주 묻는 질문</h2>
        </div>
        <div className="max-w-3xl mx-auto space-y-6">
          {faqs.map((faq, index) => (
            <Card key={index}>
              <CardHeader>
                <CardTitle className="text-lg">{faq.question}</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">{faq.answer}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="container mx-auto px-4 py-20">
        <div className="bg-gradient-to-r from-blue-600 to-cyan-600 rounded-2xl p-12 text-center text-white">
          <h2 className="text-3xl font-bold mb-4">지금 시작하세요</h2>
          <p className="text-blue-100 mb-8">
            무료 플랜으로 시작하고, 필요할 때 업그레이드하세요.
          </p>
          <Link href="/signup">
            <Button size="lg" variant="secondary" className="gap-2">
              무료로 시작하기 <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t bg-slate-50 dark:bg-slate-900">
        <div className="container mx-auto px-4 py-12">
          <div className="flex flex-col md:flex-row justify-between items-center gap-4">
            <div className="flex items-center gap-2">
              <FileText className="w-6 h-6 text-blue-600" />
              <span className="font-bold">RegistryParser</span>
            </div>
            <p className="text-sm text-muted-foreground text-center">
              등기부등본 PDF 파싱 서비스 - 디지털 PDF(텍스트 기반)만 지원합니다.
              <br />
              실제 법적 효력이 있는 등기사항증명서는 법원 등기소에서 발급받으시기 바랍니다.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
