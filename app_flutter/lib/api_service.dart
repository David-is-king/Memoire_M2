// ─────────────────────────────────────────────
// services/api_service.dart
// ─────────────────────────────────────────────

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'sensor_data.dart';

class ApiService {
  // URL REST du backend FastAPI.
  // Par defaut : machine locale. Tu peux surcharger au lancement Flutter :
  // flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
  static const Duration _timeout = Duration(seconds: 10);

  final http.Client _client;

  ApiService({http.Client? client}) : _client = client ?? http.Client();

  Map<String, String> get _headers => {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  // ── Auth ────────────────────────────────────

  Future<bool> login(String email, String password) async {
    try {
      final response = await _client.post(
        Uri.parse('$baseUrl/auth/login'),
        headers: _headers,
        body: jsonEncode({'email': email, 'password': password}),
      ).timeout(_timeout);
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  // ── Motors ──────────────────────────────────

  Future<List<MotorDevice>> getMotors() async {
    final response = await _client
        .get(Uri.parse('$baseUrl/motors'), headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((j) => MotorDevice.fromJson(j)).toList();
    }
    throw ApiException('Erreur chargement moteurs: ${response.statusCode}');
  }

  Future<MotorDevice> getMotorById(String motorId) async {
    final response = await _client
        .get(Uri.parse('$baseUrl/motors/$motorId'), headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      return MotorDevice.fromJson(jsonDecode(response.body));
    }
    throw ApiException('Moteur introuvable: $motorId');
  }

  // ── Sensor History ───────────────────────────

  Future<List<SensorReading>> getSensorHistory(
    String motorId, {
    Duration window = const Duration(hours: 1),
  }) async {
    final since = DateTime.now().subtract(window).toIso8601String();
    final uri = Uri.parse('$baseUrl/motors/$motorId/readings?since=$since');

    final response = await _client
        .get(uri, headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((j) => SensorReading.fromJson(j)).toList();
    }
    throw ApiException('Erreur historique: ${response.statusCode}');
  }

  // ── Predictions ──────────────────────────────

  Future<PredictionResult> getPrediction(String motorId) async {
    final response = await _client
        .get(Uri.parse('$baseUrl/predictions/$motorId'), headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      return PredictionResult.fromJson(jsonDecode(response.body));
    }
    throw ApiException('Erreur prédiction: ${response.statusCode}');
  }

  // ── Alerts ───────────────────────────────────

  Future<List<AlertModel>> getAlerts({bool unreadOnly = false}) async {
    final uri = Uri.parse(
      '$baseUrl/alerts${unreadOnly ? '?unread=true' : ''}',
    );

    final response = await _client
        .get(uri, headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((j) => AlertModel.fromJson(j)).toList();
    }
    throw ApiException('Erreur alertes: ${response.statusCode}');
  }

  Future<void> markAlertRead(String alertId) async {
    await _client
        .patch(
          Uri.parse('$baseUrl/alerts/$alertId/read'),
          headers: _headers,
        )
        .timeout(_timeout);
  }

  Future<void> markAllAlertsRead() async {
    await _client
        .post(
          Uri.parse('$baseUrl/alerts/mark-all-read'),
          headers: _headers,
        )
        .timeout(_timeout);
  }

  // ── Interventions ─────────────────────────────
  // NOTE: ces endpoints supposent un backend exposant
  // GET/PATCH /interventions. Si non encore implémenté côté
  // FastAPI, getInterventions() renverra une exception gérée
  // par l'écran (fallback affiché à l'utilisateur).

  Future<List<InterventionModel>> getInterventions() async {
    final response = await _client
        .get(Uri.parse('$baseUrl/interventions'), headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((j) => InterventionModel.fromJson(j)).toList();
    }
    throw ApiException('Erreur chargement interventions: ${response.statusCode}');
  }

  Future<InterventionModel> getInterventionById(String id) async {
    final response = await _client
        .get(Uri.parse('$baseUrl/interventions/$id'), headers: _headers)
        .timeout(_timeout);

    if (response.statusCode == 200) {
      return InterventionModel.fromJson(jsonDecode(response.body));
    }
    throw ApiException('Intervention introuvable: $id');
  }

  Future<void> updateInterventionStatus(String id, InterventionStatus status) async {
    await _client
        .patch(
          Uri.parse('$baseUrl/interventions/$id'),
          headers: _headers,
          body: jsonEncode({'status': status.name}),
        )
        .timeout(_timeout);
  }

  Future<void> updateInterventionProgress(String id, double progress, {String? currentStep}) async {
    await _client
        .patch(
          Uri.parse('$baseUrl/interventions/$id/progress'),
          headers: _headers,
          body: jsonEncode({
            'progress': progress,
            if (currentStep != null) 'current_step': currentStep,
          }),
        )
        .timeout(_timeout);
  }

  Future<void> addInterventionNote(String id, String note) async {
    await _client
        .post(
          Uri.parse('$baseUrl/interventions/$id/notes'),
          headers: _headers,
          body: jsonEncode({'note': note}),
        )
        .timeout(_timeout);
  }
}

class ApiException implements Exception {
  final String message;
  ApiException(this.message);

  @override
  String toString() => 'ApiException: $message';
}
