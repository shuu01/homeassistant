resource "google_cloud_run_v2_service" "whisper" {
  name     = "whisper"
  location = var.region

  template {

    containers {
      image = "docker.io/${var.user}/whisper:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "whisper_invoker" {
  project  = google_cloud_run_v2_service.whisper.project
  location = google_cloud_run_v2_service.whisper.location
  name     = google_cloud_run_v2_service.whisper.name

  role   = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.assistant.email}"
}

output "whisper_url" {
  value = google_cloud_run_v2_service.whisper.uri
}
