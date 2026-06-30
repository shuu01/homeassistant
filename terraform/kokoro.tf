resource "google_cloud_run_v2_service" "kokoro" {
  name     = "kokoro"
  location = var.region

  template {

    containers {
      image = "docker.io/${var.user}/kokoro:latest"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }

    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "kokoro_invoker" {
  project  = google_cloud_run_v2_service.kokoro.project
  location = google_cloud_run_v2_service.kokoro.location
  name     = google_cloud_run_v2_service.kokoro.name

  role   = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.assistant.email}"
}

output "kokoro_url" {
  value = google_cloud_run_v2_service.kokoro.uri
}
