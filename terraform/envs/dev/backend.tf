terraform {
  backend "gcs" {
    bucket = "cnp-eba-terraform-state-dev"
    prefix = "transmission-apprentice/dev"
  }
}