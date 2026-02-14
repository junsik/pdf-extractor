'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { XCircle } from 'lucide-react';

function PaymentFailContent() {
  const searchParams = useSearchParams();
  const code = searchParams.get('code');
  const message = searchParams.get('message');

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900 flex items-center justify-center">
      <Card className="w-full max-w-md mx-4">
        <CardHeader className="text-center">
          <XCircle className="w-16 h-16 mx-auto text-red-500" />
          <CardTitle className="mt-4 text-xl">결제에 실패했습니다</CardTitle>
        </CardHeader>
        <CardContent className="text-center space-y-4">
          <p className="text-muted-foreground">
            {message || '결제 처리 중 오류가 발생했습니다.'}
          </p>
          {code && (
            <p className="text-sm text-muted-foreground">오류 코드: {code}</p>
          )}
          <div className="flex gap-2">
            <Link href="/pricing" className="flex-1">
              <Button variant="outline" className="w-full">다시 시도</Button>
            </Link>
            <Link href="/dashboard" className="flex-1">
              <Button className="w-full">대시보드</Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function PaymentFailPage() {
  return (
    <Suspense fallback={null}>
      <PaymentFailContent />
    </Suspense>
  );
}
