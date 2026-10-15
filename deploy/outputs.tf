output "cloudfront_url" {
  description = "Link publico para compartir el visor."
  value       = "https://${aws_cloudfront_distribution.viewer.domain_name}"
}

output "cloudfront_domain" {
  description = "Dominio de la distribucion CloudFront del visor."
  value       = aws_cloudfront_distribution.viewer.domain_name
}

output "cloudfront_distribution_id" {
  description = "ID de la distribucion CloudFront creada."
  value       = aws_cloudfront_distribution.viewer.id
}
