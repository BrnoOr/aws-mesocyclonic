variable "region" {
  description = "Region de AWS donde vive la instancia."
  type        = string
  default     = "us-east-1"
}

variable "instance_id" {
  description = "ID de la instancia EC2 que hospeda el visor."
  type        = string
  default     = "i-0ea9664c5e9ada5a0"
}

variable "security_group_id" {
  description = "Security group de la instancia al que se agrega la regla del visor."
  type        = string
  default     = "sg-0f0d310ee81f4fd96"
}

variable "viewer_port" {
  description = "Puerto del host donde Docker publica el visor (8501 interno de Streamlit)."
  type        = number
  default     = 8501
}

variable "repo_url" {
  description = "URL del repositorio publico a clonar en la instancia."
  type        = string
  default     = "https://github.com/idia-tt/aws-mesocyclonic.git"
}

variable "repo_ref" {
  description = "Rama o commit del repo a desplegar. Cambiarlo fuerza un redeploy."
  type        = string
  default     = "main"
}

variable "case_date" {
  description = "Dia (YYYY-MM-DD) a descargar y procesar para el visor."
  type        = string
  default     = "2019-05-30"
}
