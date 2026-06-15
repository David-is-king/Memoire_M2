// ─────────────────────────────────────────────
// models/sensor_data.dart
// ─────────────────────────────────────────────

enum MotorStatus { healthy, warning, critical, offline }

enum AlertSeverity { info, warning, critical }

class SensorReading {
  final DateTime timestamp;
  final double temperature;    // °C
  final double vibrationRms;   // m/s²
  final double current;        // A
  final double voltage;        // V
  final double acousticDb;     // dB

  const SensorReading({
    required this.timestamp,
    required this.temperature,
    required this.vibrationRms,
    required this.current,
    required this.voltage,
    required this.acousticDb,
  });

  factory SensorReading.fromJson(Map<String, dynamic> json) {
    return SensorReading(
      timestamp: DateTime.parse(json['timestamp']),
      temperature: (json['temperature'] as num).toDouble(),
      vibrationRms: (json['vibration_rms'] as num).toDouble(),
      current: (json['current'] as num).toDouble(),
      voltage: (json['voltage'] as num).toDouble(),
      acousticDb: (json['acoustic_db'] as num).toDouble(),
    );
  }

  Map<String, dynamic> toJson() => {
    'timestamp': timestamp.toIso8601String(),
    'temperature': temperature,
    'vibration_rms': vibrationRms,
    'current': current,
    'voltage': voltage,
    'acoustic_db': acousticDb,
  };
}

class MotorDevice {
  final String id;
  final String name;
  final String location;
  final MotorStatus status;
  final double healthScore;       // 0.0 → 1.0
  final double failureProbability; // 0.0 → 1.0
  final int estimatedRulDays;     // Remaining Useful Life en jours
  final SensorReading? lastReading;
  final DateTime lastSeen;

  const MotorDevice({
    required this.id,
    required this.name,
    required this.location,
    required this.status,
    required this.healthScore,
    required this.failureProbability,
    required this.estimatedRulDays,
    this.lastReading,
    required this.lastSeen,
  });

  factory MotorDevice.fromJson(Map<String, dynamic> json) {
    return MotorDevice(
      id: json['id'],
      name: json['name'],
      location: json['location'],
      status: MotorStatus.values.byName(json['status']),
      healthScore: (json['health_score'] as num).toDouble(),
      failureProbability: (json['failure_probability'] as num).toDouble(),
      estimatedRulDays: json['estimated_rul_days'],
      lastReading: json['last_reading'] != null
          ? SensorReading.fromJson(json['last_reading'])
          : null,
      lastSeen: DateTime.parse(json['last_seen']),
    );
  }
}

class PredictionResult {
  final String motorId;
  final DateTime predictedAt;
  final double failureProbability;
  final MotorStatus recommendedStatus;
  final String maintenanceRecommendation;
  final List<String> anomalyFeatures;
  final int estimatedRulDays;

  const PredictionResult({
    required this.motorId,
    required this.predictedAt,
    required this.failureProbability,
    required this.recommendedStatus,
    required this.maintenanceRecommendation,
    required this.anomalyFeatures,
    required this.estimatedRulDays,
  });

  factory PredictionResult.fromJson(Map<String, dynamic> json) {
    return PredictionResult(
      motorId: json['motor_id'],
      predictedAt: DateTime.parse(json['predicted_at']),
      failureProbability: (json['failure_probability'] as num).toDouble(),
      recommendedStatus: MotorStatus.values.byName(json['recommended_status']),
      maintenanceRecommendation: json['maintenance_recommendation'],
      anomalyFeatures: List<String>.from(json['anomaly_features']),
      estimatedRulDays: json['estimated_rul_days'],
    );
  }
}

class AlertModel {
  final String id;
  final String motorId;
  final String motorName;
  final AlertSeverity severity;
  final String title;
  final String message;
  final DateTime createdAt;
  final bool isRead;

  const AlertModel({
    required this.id,
    required this.motorId,
    required this.motorName,
    required this.severity,
    required this.title,
    required this.message,
    required this.createdAt,
    required this.isRead,
  });

  factory AlertModel.fromJson(Map<String, dynamic> json) {
    return AlertModel(
      id: json['id'],
      motorId: json['motor_id'],
      motorName: json['motor_name'],
      severity: AlertSeverity.values.byName(json['severity']),
      title: json['title'],
      message: json['message'],
      createdAt: DateTime.parse(json['created_at']),
      isRead: json['is_read'],
    );
  }
}

class ChartDataPoint {
  final DateTime time;
  final double value;
  const ChartDataPoint({required this.time, required this.value});
}
