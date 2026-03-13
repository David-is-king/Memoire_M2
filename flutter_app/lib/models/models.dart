// lib/models/models.dart

enum DeviceStatus { healthy, warning, critical, offline }
enum AlertSeverity { critical, warning, info, ok }

class MotorDevice {
  final String id;
  final String name;
  final String location;
  final DeviceStatus status;
  final int healthScore;       // 0–100
  final double failureProb;    // 0.0–1.0
  final int rulDays;
  final SensorReading? lastReading;
  final DateTime lastSeen;
  final bool isActive;

  const MotorDevice({
    required this.id, required this.name, required this.location,
    required this.status, required this.healthScore, required this.failureProb,
    required this.rulDays, this.lastReading, required this.lastSeen, required this.isActive,
  });

  factory MotorDevice.fromJson(Map<String, dynamic> j) => MotorDevice(
    id: j['id'], name: j['name'], location: j['location'],
    status: DeviceStatus.values.byName(j['status']),
    healthScore: j['health_score'], failureProb: (j['failure_prob'] as num).toDouble(),
    rulDays: j['rul_days'],
    lastReading: j['last_reading'] != null ? SensorReading.fromJson(j['last_reading']) : null,
    lastSeen: DateTime.parse(j['last_seen']), isActive: j['is_active'],
  );
}

class SensorReading {
  final DateTime timestamp;
  final double temperature;  // °C
  final double vibration;    // g
  final double current;      // A
  final double voltage;      // V
  final double acousticDb;   // dB
  final double speedRpm;

  const SensorReading({
    required this.timestamp, required this.temperature, required this.vibration,
    required this.current, required this.voltage, required this.acousticDb, required this.speedRpm,
  });

  factory SensorReading.fromJson(Map<String, dynamic> j) => SensorReading(
    timestamp: DateTime.parse(j['timestamp']),
    temperature: (j['temperature'] as num).toDouble(),
    vibration: (j['vibration'] as num).toDouble(),
    current: (j['current'] as num).toDouble(),
    voltage: (j['voltage'] as num).toDouble(),
    acousticDb: (j['acoustic_db'] as num).toDouble(),
    speedRpm: (j['speed_rpm'] as num).toDouble(),
  );
}

class ChartPoint {
  final DateTime time;
  final double value;
  const ChartPoint({required this.time, required this.value});
}

class AlertItem {
  final String id;
  final String deviceId;
  final String deviceName;
  final AlertSeverity severity;
  final String title;
  final String message;
  final DateTime createdAt;
  final bool isRead;

  const AlertItem({
    required this.id, required this.deviceId, required this.deviceName,
    required this.severity, required this.title, required this.message,
    required this.createdAt, required this.isRead,
  });

  factory AlertItem.fromJson(Map<String, dynamic> j) => AlertItem(
    id: j['id'], deviceId: j['device_id'], deviceName: j['device_name'],
    severity: AlertSeverity.values.byName(j['severity']),
    title: j['title'], message: j['message'],
    createdAt: DateTime.parse(j['created_at']), isRead: j['is_read'],
  );

  AlertItem copyWith({bool? isRead}) => AlertItem(
    id: id, deviceId: deviceId, deviceName: deviceName, severity: severity,
    title: title, message: message, createdAt: createdAt, isRead: isRead ?? this.isRead,
  );
}

class PredictionResult {
  final String deviceId;
  final DateTime predictedAt;
  final double failureProb;
  final int rulDays;
  final String recommendation;
  final List<String> anomalies;
  final DeviceStatus suggestedStatus;

  const PredictionResult({
    required this.deviceId, required this.predictedAt, required this.failureProb,
    required this.rulDays, required this.recommendation, required this.anomalies,
    required this.suggestedStatus,
  });

  factory PredictionResult.fromJson(Map<String, dynamic> j) => PredictionResult(
    deviceId: j['device_id'], predictedAt: DateTime.parse(j['predicted_at']),
    failureProb: (j['failure_prob'] as num).toDouble(), rulDays: j['rul_days'],
    recommendation: j['recommendation'],
    anomalies: List<String>.from(j['anomalies']),
    suggestedStatus: DeviceStatus.values.byName(j['suggested_status']),
  );
}