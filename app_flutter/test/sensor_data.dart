enum AlertSeverity { critical, warning, info }

class AlertModel {
  final String id;
  final String motorId;
  final String motorName;
  final AlertSeverity severity;
  final String title;
  final String message;
  final DateTime createdAt;
  final bool isRead;

  AlertModel({
    required this.id,
    required this.motorId,
    required this.motorName,
    required this.severity,
    required this.title,
    required this.message,
    required this.createdAt,
    this.isRead = false,
  });
}