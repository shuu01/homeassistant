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
