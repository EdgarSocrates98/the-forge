# Planted: public S3 bucket + open security group (P5).
resource "aws_s3_bucket" "reports" { bucket = "pay-reports" }
resource "aws_security_group" "open" {
  ingress { from_port = 0; to_port = 65535; cidr_blocks = ["0.0.0.0/0"] }
}
