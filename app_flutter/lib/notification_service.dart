import 'sensor_data.dart';

class NotificationService {
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  NotificationService._internal();

  Future<void> initialize() async {
    return;
  }

  Future<void> showAlertNotification(AlertModel alert) async {
    await initialize();
  }

  Future<void> showCriticalBanner({
    required String motorName,
    required String message,
    required String motorId,
  }) async {
    await initialize();
  }
}
