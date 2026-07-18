export type UserRole = 'INDIVIDUAL' | 'ADVISOR' | 'ADMIN' | 'HOUSEHOLD';

export interface User {
  id: string;
  email: string;
  display_name: string;
  roles: UserRole[];
  mfa_enabled: boolean;
  status: string;
}

export interface LoginResult {
  success: boolean;
  mfaRequired?: boolean;
  challengeToken?: string;
  error?: string;
}

export interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  sessionExpired: boolean;
  clearSessionExpired: () => void;
  refreshUser: () => Promise<void>;
  login: (email: string, password: string) => Promise<LoginResult>;
  loginMfa: (challengeToken: string, totpCode: string) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
}

// FR-08 — GET /api/dashboard response (all monetary values are decimal strings)
export interface CategorySpend {
  category: string;
  total: string;
}

export interface TrendPoint {
  month: string; // YYYY-MM
  spend: string;
  income: string;
}

export interface MerchantSpend {
  merchant: string;
  total: string;
}

export interface DashboardData {
  month: string; // YYYY-MM
  spending_by_category: CategorySpend[];
  monthly_trend: TrendPoint[];
  top_merchants: MerchantSpend[];
}

export type CategoryType = 'EXPENSE' | 'INCOME';

// FR-06 — GET /api/categories item
export interface CategoryRecord {
  id: string;
  name: string;
  type: CategoryType;
  is_global: boolean;
}

// FR-06 — a transaction as serialized by GET/POST/PATCH /api/transactions
export interface TransactionRecord {
  id: string;
  transaction_date: string; // YYYY-MM-DD
  amount: string; // positive decimal string
  type: CategoryType; // from its category
  category: string; // category name
  category_id: string;
  merchant_name: string | null;
  description: string | null;
}

// FR-07 — a file category that doesn't exist yet, with a suggested type.
export interface UnknownCategory {
  name: string;
  suggested_type: CategoryType;
}

// FR-07 — POST /api/statements/upload response (Phase A: analyze).
export interface UploadResponse {
  statement_id: string;
  status: 'PROCESSED' | 'FAILED' | 'NEEDS_CATEGORIES';
  imported_count?: number;
  skipped_count?: number;
  total_rows?: number;
  unknown_categories?: UnknownCategory[];
}

// FR-07 — POST /api/statements/<id>/import response (Phase C: confirm).
export interface ImportResponse {
  statement_id: string;
  status: string; // PROCESSED
  imported_count: number;
  skipped_count: number;
}

// FR-09 — a household summary-access grant (GET/POST /api/consents/household)
export interface HouseholdShare {
  id: string;
  grantee_id: string;
  grantee_email: string | null;
  grantee_display_name: string | null;
  grantee_status: string | null; // ACTIVE once they've signed up, PENDING while invited
  access_level: string;
  status: string;
  created_at: string;
}

// FR-15 — one grantor's shared summary (GET /api/household/summary → grantors[])
export interface HouseholdGrantorSummary {
  grantor_id: string;
  grantor_display_name: string | null;
  spending_by_category: CategorySpend[];
  monthly_trend: TrendPoint[];
}

// FR-10 — an advisor access grant reuses the same consent shape as a household share.
export type AdvisorShare = HouseholdShare;

// FR-16 — a client an advisor can view (GET /api/advisor/clients → clients[])
export interface AdvisorClient {
  grantor_id: string;
  display_name: string | null;
}

// FR-16 — GET /api/advisor/clients/:id/analytics
export interface AdvisorClientAnalytics {
  grantor_id: string;
  display_name: string | null;
  analytics: DashboardData;
}

// SR-16 — GET /api/admin/audit-logs
export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  event_type: string;
  resource_id: string | null;
  outcome: string;
  ip_address: string | null;
  user_agent: string | null;
  timestamp: string;
}

export interface AuditLogsResponse {
  items: AuditLogEntry[];
  page: number;
  page_size: number;
  total: number;
}

// Legacy types used by other team members' pages — kept for compatibility
export interface Transaction {
  id: string;
  date: string;
  description: string;
  amount: number;
  category: string;
  type: 'expense' | 'income';
}

export interface Client {
  id: string;
  name: string;
  email: string;
  consentStatus: 'granted' | 'revoked';
  lastViewed?: string;
}
