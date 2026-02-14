// API 클라이언트
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface FetchOptions extends RequestInit {
  token?: string;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('access_token');
  }

  private setToken(token: string) {
    if (typeof window === 'undefined') return;
    localStorage.setItem('access_token', token);
  }

  private removeToken() {
    if (typeof window === 'undefined') return;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  async fetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
    const token = this.getToken();
    const headers: HeadersInit = {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    };

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      this.removeToken();
      if (typeof window !== 'undefined') {
        window.location.href = '/login';
      }
      throw new Error('인증이 만료되었습니다.');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: '알 수 없는 오류' }));
      throw new Error(error.detail || 'API 요청 실패');
    }

    return response.json();
  }

  // 인증
  async signup(data: { email: string; password: string; name: string; phone?: string; company?: string }) {
    return this.fetch<{ success: boolean; message: string }>('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async login(data: { email: string; password: string }) {
    const response = await this.fetch<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
    }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });

    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', response.access_token);
      localStorage.setItem('refresh_token', response.refresh_token);
    }

    return response;
  }

  logout() {
    this.removeToken();
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  }

  async getMe() {
    return this.fetch<{
      id: number;
      email: string;
      name: string;
      phone?: string;
      company?: string;
      role: string;
      plan: string;
      plan_end_date?: string;
      credits: number;
      credits_used: number;
      webhook_enabled: boolean;
      webhook_url?: string;
      api_key?: string;
      created_at: string;
    }>('/api/auth/me');
  }

  // PDF 파싱
  async parsePdf(file: File, demoMode: boolean = false, webhookUrl?: string) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('demo_mode', demoMode.toString());
    if (webhookUrl) {
      formData.append('webhook_url', webhookUrl);
    }

    return this.fetch<{
      success: boolean;
      request_id: string;
      status: string;
      data?: any;
      error?: string;
      is_demo: boolean;
      remaining_credits: number;
    }>('/api/parse', {
      method: 'POST',
      body: formData,
    });
  }

  async getParseHistory(page: number = 1, pageSize: number = 20) {
    return this.fetch<{
      success: boolean;
      items: any[];
      total: number;
      page: number;
      page_size: number;
    }>(`/api/parse/history?page=${page}&page_size=${pageSize}`);
  }

  // 결제
  async getPricing() {
    return this.fetch<{
      plans: Array<{
        type: string;
        name: string;
        price: number;
        credits: number;
        features: string[];
      }>;
    }>('/api/pricing');
  }

  async getTossClientKey() {
    return this.fetch<{ client_key: string }>('/api/payment/client-key');
  }

  async createPayment(data: { plan_type: string; success_url: string; fail_url: string }) {
    return this.fetch<{
      success: boolean;
      order_id: string;
      order_name: string;
      amount: number;
      plan_type: string;
      customer_name: string;
      customer_email: string;
    }>('/api/payment/create', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async confirmPayment(data: { payment_key: string; order_id: string; amount: number }) {
    return this.fetch<{ success: boolean; message: string }>('/api/payment/confirm', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getPaymentHistory() {
    return this.fetch<{
      success: boolean;
      items: any[];
      total: number;
    }>('/api/payment/history');
  }

  // 설정
  async updateWebhookSettings(data: { enabled: boolean; url?: string; secret?: string }) {
    return this.fetch<{ success: boolean; message: string }>('/api/webhook/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async updateUserSettings(data: { name?: string; phone?: string; company?: string }) {
    return this.fetch<{ success: boolean; message: string }>('/api/user/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async regenerateApiKey() {
    return this.fetch<{ success: boolean; api_key: string }>('/api/user/api-key/regenerate', {
      method: 'POST',
    });
  }

  // 헬스 체크
  async healthCheck() {
    return this.fetch<{ status: string; service: string; version: string }>('/health');
  }
}

export const api = new ApiClient(API_BASE);
