variable "subscription_id" {
  description = "Subscription to deploy into. Named explicitly so a CLI logged into another subscription cannot receive this deployment by default."
  type        = string
}

variable "prefix" {
  description = "Short resource-name prefix (lowercase alphanumerics and hyphens). The resource group is rg-<prefix>."
  type        = string
  default     = "madison-ai"
}

variable "location" {
  description = "Azure region."
  type        = string
  default     = "australiaeast"
}

variable "image_repo" {
  description = "Public image repository prefix: <this>/frontend:<tag> and <this>/backend:<tag>. Public, so the app pulls with no credential."
  type        = string
  default     = "ghcr.io/wenhuaiqing/madison-ai-solutions"
}

variable "image_tag" {
  description = "Tag for both images (the short commit SHA)."
  type        = string
  default     = "latest"
}

variable "min_replicas" {
  description = "0 scales to zero when idle and costs nothing, at the price of a cold start of a few seconds. 1 keeps a replica warm and is billed every second once the monthly free grant is used."
  type        = number
  default     = 0
}

variable "budget_alert_email" {
  description = "Where the monthly cost alert goes."
  type        = string
}

variable "budget_aud" {
  description = "Monthly budget for the resource group, in the subscription's currency. A tripwire, not a cap."
  type        = number
  default     = 3
}

variable "llm_base_url" {
  description = "OpenAI-protocol endpoint for the triage agent."
  type        = string
  default     = "https://generativelanguage.googleapis.com/v1beta/openai/"
}

variable "llm_api_key" {
  description = "Key for that endpoint. Empty deploys without a model: the runbook answers and the page says so."
  type        = string
  sensitive   = true
  default     = ""
}

variable "llm_chat_model" {
  description = "Model for triage. A small, fast one: a triage is three to six sequential calls."
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "llm_fallback_model" {
  description = "Tried once when the primary answers 429 or 5xx."
  type        = string
  default     = "gemini-3.1-flash-lite"
}
