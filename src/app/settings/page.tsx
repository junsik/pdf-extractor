'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  FileText,
  User,
  Webhook,
  Key,
  Loader2,
  LogOut,
  Settings,
  Copy,
  Check,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { api } from '@/lib/api';

export default function SettingsPage() {
  const { user, isLoading: authLoading, logout, refreshUser } = useAuth();
  const router = useRouter();

  const [profileForm, setProfileForm] = useState({
    name: '',
    phone: '',
    company: '',
  });
  const [webhookForm, setWebhookForm] = useState({
    enabled: false,
    url: '',
    secret: '',
  });
  const [showApiKey, setShowApiKey] = useState(false);
  const [copied, setCopied] = useState(false);

  const [isSaving, setIsSaving] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login');
    }
    if (user) {
      setProfileForm({
        name: user.name || '',
        phone: user.phone || '',
        company: user.company || '',
      });
      setWebhookForm({
        enabled: user.webhook_enabled || false,
        url: user.webhook_url || '',
        secret: '',
      });
    }
  }, [user, authLoading, router]);

  const handleSaveProfile = async () => {
    setIsSaving(true);
    setMessage({ type: '', text: '' });
    try {
      await api.updateUserSettings(profileForm);
      await refreshUser();
      setMessage({ type: 'success', text: '프로필이 저장되었습니다.' });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '저장에 실패했습니다.' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveWebhook = async () => {
    setIsSaving(true);
    setMessage({ type: '', text: '' });
    try {
      await api.updateWebhookSettings(webhookForm);
      await refreshUser();
      setMessage({ type: 'success', text: 'Webhook 설정이 저장되었습니다.' });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '저장에 실패했습니다.' });
    } finally {
      setIsSaving(false);
    }
  };

  const handleRegenerateApiKey = async () => {
    if (!confirm('API 키를 재발급하시겠습니까? 기존 키는 즉시 사용할 수 없게 됩니다.')) {
      return;
    }

    setIsRegenerating(true);
    try {
      const result = await api.regenerateApiKey();
      await refreshUser();
      setMessage({ type: 'success', text: 'API 키가 재발급되었습니다.' });
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message || '재발급에 실패했습니다.' });
    } finally {
      setIsRegenerating(false);
    }
  };

  const handleCopyApiKey = () => {
    if (user?.api_key) {
      navigator.clipboard.writeText(user.api_key);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleLogout = () => {
    logout();
  };

  if (authLoading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white dark:from-slate-950 dark:to-slate-900">
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
            <Link href="/dashboard">
              <Button variant="ghost">대시보드</Button>
            </Link>
            <Button variant="ghost" onClick={handleLogout}>
              <LogOut className="w-4 h-4 mr-1" />
              로그아웃
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-2xl mx-auto space-y-6">
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Settings className="w-8 h-8" />
            설정
          </h1>

          {message.text && (
            <div
              className={`p-4 rounded-lg ${
                message.type === 'success'
                  ? 'bg-green-50 text-green-700 dark:bg-green-950/20 dark:text-green-400'
                  : 'bg-red-50 text-red-700 dark:bg-red-950/20 dark:text-red-400'
              }`}
            >
              {message.text}
            </div>
          )}

          {/* Profile */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="w-5 h-5" />
                프로필
              </CardTitle>
              <CardDescription>계정 정보를 관리하세요.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="email">이메일</Label>
                <Input id="email" value={user.email} disabled className="bg-slate-50" />
              </div>
              <div>
                <Label htmlFor="name">이름</Label>
                <Input
                  id="name"
                  value={profileForm.name}
                  onChange={(e) => setProfileForm((p) => ({ ...p, name: e.target.value }))}
                />
              </div>
              <div>
                <Label htmlFor="phone">연락처</Label>
                <Input
                  id="phone"
                  value={profileForm.phone}
                  onChange={(e) => setProfileForm((p) => ({ ...p, phone: e.target.value }))}
                />
              </div>
              <div>
                <Label htmlFor="company">회사명</Label>
                <Input
                  id="company"
                  value={profileForm.company}
                  onChange={(e) => setProfileForm((p) => ({ ...p, company: e.target.value }))}
                />
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleSaveProfile} disabled={isSaving}>
                {isSaving ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    저장 중...
                  </>
                ) : (
                  '저장'
                )}
              </Button>
            </CardFooter>
          </Card>

          {/* API Key */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Key className="w-5 h-5" />
                API 키
              </CardTitle>
              <CardDescription>
                API를 통해 프로그래밍 방식으로 접근할 수 있습니다.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>API 키</Label>
                <div className="flex gap-2 mt-1">
                  <Input
                    type={showApiKey ? 'text' : 'password'}
                    value={user.api_key || ''}
                    disabled
                    className="font-mono"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => setShowApiKey(!showApiKey)}
                  >
                    {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </Button>
                  <Button variant="outline" size="icon" onClick={handleCopyApiKey}>
                    {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  </Button>
                </div>
              </div>
            </CardContent>
            <CardFooter>
              <Button
                variant="outline"
                onClick={handleRegenerateApiKey}
                disabled={isRegenerating}
              >
                {isRegenerating ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    재발급 중...
                  </>
                ) : (
                  'API 키 재발급'
                )}
              </Button>
            </CardFooter>
          </Card>

          {/* Webhook */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Webhook className="w-5 h-5" />
                Webhook 설정
              </CardTitle>
              <CardDescription>
                파싱 완료 시 지정된 URL로 결과를 전송합니다.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <Label htmlFor="webhook-enabled">Webhook 사용</Label>
                <Switch
                  id="webhook-enabled"
                  checked={webhookForm.enabled}
                  onCheckedChange={(checked) =>
                    setWebhookForm((p) => ({ ...p, enabled: checked }))
                  }
                />
              </div>
              {webhookForm.enabled && (
                <>
                  <div>
                    <Label htmlFor="webhook-url">Webhook URL</Label>
                    <Input
                      id="webhook-url"
                      type="url"
                      placeholder="https://your-server.com/webhook"
                      value={webhookForm.url}
                      onChange={(e) => setWebhookForm((p) => ({ ...p, url: e.target.value }))}
                    />
                  </div>
                  <div>
                    <Label htmlFor="webhook-secret">Secret (선택)</Label>
                    <Input
                      id="webhook-secret"
                      type="password"
                      placeholder="Webhook 검증용 시크릿"
                      value={webhookForm.secret}
                      onChange={(e) => setWebhookForm((p) => ({ ...p, secret: e.target.value }))}
                    />
                  </div>
                </>
              )}
            </CardContent>
            <CardFooter>
              <Button onClick={handleSaveWebhook} disabled={isSaving}>
                {isSaving ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    저장 중...
                  </>
                ) : (
                  '저장'
                )}
              </Button>
            </CardFooter>
          </Card>

          {/* Plan */}
          <Card>
            <CardHeader>
              <CardTitle>현재 플랜</CardTitle>
              <CardDescription>
                플랜 정보 및 변경
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-lg">
                    {user.plan === 'free' ? '무료' : user.plan === 'basic' ? '베이직' : '프로'} 플랜
                  </p>
                  <p className="text-sm text-muted-foreground">
                    남은 크레딧: {user.credits === -1 ? '무제한' : user.credits}회
                  </p>
                </div>
                <Link href="/pricing">
                  <Button variant="outline">플랜 변경</Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
