'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { CheckCircle2, Loader2, XCircle, FileText } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';

function PaymentSuccessContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [errorMessage, setErrorMessage] = useState('');

  useEffect(() => {
    confirmPayment();
  }, []);

  const confirmPayment = async () => {
    const paymentKey = searchParams.get('paymentKey');
    const orderId = searchParams.get('orderId');
    const amount = searchParams.get('amount');

    if (!paymentKey || !orderId || !amount) {
      setStatus('error');
      setErrorMessage('결제 정보가 올바르지 않습니다.');
      return;
    }

    try {
      await api.confirmPayment({
        payment_key: paymentKey,
        order_id: orderId,
        amount: Number(amount),
      });
      await refreshUser();
      setStatus('success');
    } catch (error) {
      setStatus('error');
      setErrorMessage(error instanceof Error ? error.message : '결제 승인에 실패했습니다.');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900 flex items-center justify-center">
      <Card className="w-full max-w-md mx-4">
        <CardHeader className="text-center">
          {status === 'loading' && (
            <>
              <Loader2 className="w-16 h-16 mx-auto text-blue-600 animate-spin" />
              <CardTitle className="mt-4 text-xl">결제 승인 중...</CardTitle>
            </>
          )}
          {status === 'success' && (
            <>
              <CheckCircle2 className="w-16 h-16 mx-auto text-green-500" />
              <CardTitle className="mt-4 text-xl">결제가 완료되었습니다</CardTitle>
            </>
          )}
          {status === 'error' && (
            <>
              <XCircle className="w-16 h-16 mx-auto text-red-500" />
              <CardTitle className="mt-4 text-xl">결제 승인 실패</CardTitle>
            </>
          )}
        </CardHeader>
        <CardContent className="text-center space-y-4">
          {status === 'loading' && (
            <p className="text-muted-foreground">잠시만 기다려주세요...</p>
          )}
          {status === 'success' && (
            <>
              <p className="text-muted-foreground">
                요금제가 업그레이드되었습니다. 대시보드에서 확인해보세요.
              </p>
              <Link href="/dashboard">
                <Button className="w-full">대시보드로 이동</Button>
              </Link>
            </>
          )}
          {status === 'error' && (
            <>
              <p className="text-muted-foreground">{errorMessage}</p>
              <div className="flex gap-2">
                <Link href="/pricing" className="flex-1">
                  <Button variant="outline" className="w-full">요금제 페이지</Button>
                </Link>
                <Link href="/dashboard" className="flex-1">
                  <Button className="w-full">대시보드</Button>
                </Link>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function PaymentSuccessPage() {
  return (
    <Suspense fallback={null}>
      <PaymentSuccessContent />
    </Suspense>
  );
}
