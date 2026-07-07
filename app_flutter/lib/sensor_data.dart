// ─────────────────────────────────────────────
// models/sensor_data.dart
// ─────────────────────────────────────────────

enum MotorStatus { healthy, warning, critical, offline }

enum AlertSeverity { info, warning, critical }

enum InterventionStatus { todo, inProgress, done }

enum InterventionPriority { low, normal, major, critical }

/// Modèle d'intervention de maintenance.
/// Mappé sur un éventuel endpoint /interventions du backend.
/// Les champs JSON utilisent le snake_case habituel du reste de l'API.
class InterventionModel {
  final String id;
  final String motorId;
  final String motorName;
  final String motorLocation;
  final InterventionStatus status;
  final InterventionPriority priority;
  final String type;
  final String description;
  final DateTime scheduledAt;
  final List<InterventionChecklistItem> checklist;
  final double progress; // 0.0 -> 1.0
  final String? currentStep;
  final List<String> notes;
  final List<String> photoUrls;

  const InterventionModel({
    required this.id,
    required this.motorId,
    required this.motorName,
    required this.motorLocation,
    required this.status,
    required this.priority,
    required this.type,
    required this.description,
    required this.scheduledAt,
    this.checklist = const [],
    this.progress = 0.0,
    this.currentStep,
    this.notes = const [],
    this.photoUrls = const [],
  });

  factory InterventionModel.fromJson(Map<String, dynamic> json) {
    return InterventionModel(
      id: json['id'],
      motorId: json['motor_id'],
      motorName: json['motor_name'],
      motorLocation: json['motor_location'] ?? '',
      status: InterventionStatus.values.byName(json['status']),
      priority: InterventionPriority.values.byName(json['priority']),
      type: json['type'] ?? '',
      description: json['description'] ?? '',
      scheduledAt: DateTime.parse(json['scheduled_at']),
      checklist: json['checklist'] != null
          ? List<Map<String, dynamic>>.from(json['checklist'])
              .map((c) => InterventionChecklistItem.fromJson(c))
              .toList()
          : [],
      progress: json['progress'] != null ? (json['progress'] as num).toDouble() : 0.0,
      currentStep: json['current_step'],
      notes: json['notes'] != null ? List<String>.from(json['notes']) : [],
      photoUrls: json['photo_urls'] != null ? List<String>.from(json['photo_urls']) : [],
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'motor_id': motorId,
        'motor_name': motorName,
        'motor_location': motorLocation,
        'status': status.name,
        'priority': priority.name,
        'type': type,
        'description': description,
        'scheduled_at': scheduledAt.toIso8601String(),
        'checklist': checklist.map((c) => c.toJson()).toList(),
        'progress': progress,
        'current_step': currentStep,
        'notes': notes,
        'photo_urls': photoUrls,
      };

  InterventionModel copyWith({
    InterventionStatus? status,
    double? progress,
    String? currentStep,
    List<String>? notes,
    List<String>? photoUrls,
    List<InterventionChecklistItem>? checklist,
  }) {
    return InterventionModel(
      id: id,
      motorId: motorId,
      motorName: motorName,
      motorLocation: motorLocation,
      status: status ?? this.status,
      priority: priority,
      type: type,
      description: description,
      scheduledAt: scheduledAt,
      checklist: checklist ?? this.checklist,
      progress: progress ?? this.progress,
      currentStep: currentStep ?? this.currentStep,
      notes: notes ?? this.notes,
      photoUrls: photoUrls ?? this.photoUrls,
    );
  }
}

class InterventionChecklistItem {
  final String label;
  final bool done;

  const InterventionChecklistItem({required this.label, this.done = false});

  factory InterventionChecklistItem.fromJson(Map<String, dynamic> json) =>
      InterventionChecklistItem(label: json['label'], done: json['done'] ?? false);

  Map<String, dynamic> toJson() => {'label': label, 'done': done};

  InterventionChecklistItem copyWith({bool? done}) =>
      InterventionChecklistItem(label: label, done: done ?? this.done);
}

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
