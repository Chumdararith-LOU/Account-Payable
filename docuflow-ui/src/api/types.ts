// Shapes returned by the APMatch API (apmatch/api/schemas.py).

export type Route = 'AUTO_APPROVE' | 'HUMAN_REVIEW' | 'REJECT';

export interface Failure {
  code: string;
  severity: string;
  location: string;
  expected: string;
  actual: string;
  delta: string;
  message: string;
}

export interface RecentRun {
  run_id: string;
  run_timestamp: string;
  invoice_number: string;
  route: Route;
  route_reason: string;
  score: number;
  remark: string;
  case_id: string | null;
  customer_id: string;
  decided_by: string;
}

export interface LineItem {
  line_no: number;
  description: string;
  quantity: string | null;
  unit_price: string | null;
  amount: string | null;
  unit_of_measure?: string | null;
}

// Canonical documents: every value is a string (decimals and ISO dates) or null.
export type Doc = Record<string, unknown> & { line_items?: LineItem[] };

export interface Documents {
  invoice: Doc | null;
  po: Doc | null;
  grni: Doc | null;
  pard: Doc | null;
  _extraction?: unknown;
}

export interface AuditDetail {
  run_id: string;
  run_timestamp: string;
  route: Route;
  route_reason: string;
  score: number;
  remark: string;
  invoice_number: string;
  po_number: string | null;
  grn_number: string | null;
  pard_ref: string | null;
  validation_failures: Failure[];
  match_failures: Failure[];
  input_hash: string;
  customer_id: string;
  extraction_source: string;
  extracted: Documents | null;
  case_id: string | null;
  decided_by: string;
  history: RecentRun[];
}

export interface RouteCounts {
  auto_approve: number;
  human_review: number;
  reject: number;
  total: number;
}

export interface CodeCount {
  code: string;
  count: number;
}

// Plain-English labels for the route reasons shown to clerks.
export const REASON_LABELS: Record<string, string> = {
  ALL_CHECKS_PASSED: 'All checks passed',
  VALIDATION_BLOCKER: 'Invoice arithmetic is wrong',
  MATCH_DISCREPANCY: 'Documents do not agree',
  MATCH_PENDING_INFO: 'A document is missing',
  LOW_OCR_CONFIDENCE: 'Scan hard to read',
  LOW_OVERALL_SCORE: 'Low confidence',
  UNREADABLE_FIELD: 'A field could not be read',
  REVIEWER_APPROVED: 'Approved by reviewer',
  REVIEWER_REJECTED: 'Rejected by reviewer',
};

export function reasonLabel(reason: string): string {
  return REASON_LABELS[reason] ?? reason;
}
