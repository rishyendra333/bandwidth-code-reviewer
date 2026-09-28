variable "teammate_user_arns" {
  description = "Exact IAM user ARNs approved for cross-account inspection."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for arn in var.teammate_user_arns : can(regex("^arn:aws:iam::[0-9]{12}:user/.+$", arn))])
    error_message = "Trust exact IAM user ARNs, not entire accounts or wildcard principals."
  }
}

variable "permissions_boundary_arn" {
  description = "Bandwidth-required boundary for the project IAM roles, if applicable."
  type        = string
  default     = null
}

variable "trigger" {
  type    = string
  default = "@bandwidth-reviewer-dev"
  validation {
    condition     = can(regex("^@[A-Za-z0-9_-]+$", var.trigger))
    error_message = "The trigger must be one @name token."
  }
}

locals {
  prefix = "bandwidth-reviewer-dev"
}
