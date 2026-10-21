export type OperationState =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "timed_out";

export interface UIErrorDetail {
  code: string;
  message: string;
  retryable: boolean;
  request_id?: string | null;
  details?: unknown;
}

/** The server retains the legacy detail field while exposing this stable envelope. */
export interface UIErrorEnvelope {
  error: UIErrorDetail;
  detail?: unknown;
}

export interface OperationStatus {
  operation_id: string;
  state: OperationState;
  request_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  progress?: number | null;
  message?: string | null;
  result?: unknown;
  error?: UIErrorDetail | null;
  requires_approval: boolean;
}

export interface UIContractResponse {
  contract_version: "1.0";
  request_id_header: "X-Request-ID";
  operation_states: OperationState[];
  error_fields: string[];
  security: Record<string, string>;
  endpoints: Record<string, string>;
}
