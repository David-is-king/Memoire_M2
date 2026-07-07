// import 'package:app_flutter/sensor_data.dart';

// class ApiService {
//   Future<List<AlertModel>> getAlerts() async {
//     // Simulation d'appel API
//     return [];
//   }

//   Future<void> markAllAlertsRead() async {}
//   Future<void> markAlertRead(String id) async {}
// }

import 'dart:convert';
import 'package:app_flutter/sensor_data.dart';
import 'package:http/http.dart' as http;

class ApiService {
  // Meme URL par defaut que le service principal du dossier lib.
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  Future<bool> login(String email, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}),
      );
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  Future<List<AlertModel>> getAlerts() async {
    // Simulation d'appel API
    return [];
  }

  Future<void> markAllAlertsRead() async {}
  Future<void> markAlertRead(String id) async {}
}
