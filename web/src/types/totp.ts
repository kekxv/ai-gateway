// TOTP types
export interface TotpSetupResponse {
  secret: string
  qrCodeDataUrl: string
}

export interface TotpVerifyRequest {
  token: string
}

export interface TotpDisableRequest {
  password: string
  token: string
}