terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

variable "project" {}
variable "region" {
  default = "asia-southeast1"
}
variable "user" {}
variable "redeploy" {
  type    = string
  default = ""
}

resource "google_project_service" "run" {
  service = "run.googleapis.com"
}

resource "google_service_account" "assistant" {
  account_id   = "assistant"
  display_name = "Home Assistant"
}

resource "google_service_account_key" "assistant" {
  service_account_id = google_service_account.assistant.name
}

resource "local_file" "assistant_key" {
  filename = "assistant.key.json"
  content  = base64decode(google_service_account_key.assistant.private_key)
}
