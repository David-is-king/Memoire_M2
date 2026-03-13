// lib/services/api_service.dart

import 'dart:convert';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class ApiService {
  static const _base = 'http://localhost:8000/api/v1';
  static const _to   = Duration(seconds: 12);
  final _c = http.Client();

  final _h = const {'Content-Type': 'application/json', 'Accept': 'application/json'};

  Future<T> _get<T>(String path, T Function(dynamic) parse) async {
    final res = await _c.get(Uri.parse('$_base$path'), headers: _h).timeout(_to);
    if (res.statusCode == 200) return parse(jsonDecode(res.body));
    throw Exception('GET $path → ${res.statusCode}');
  }

  Future<List<MotorDevice>> getDevices() =>
      _get('/devices', (d) => (d as List).map((e) => MotorDevice.fromJson(e)).toList());

  Future<MotorDevice> getDevice(String id) =>
      _get('/devices/$id', (data) => MotorDevice.fromJson(data));

  Future<List<SensorReading>> getHistory(String id, {Duration window = const Duration(hours: 24)}) {
    final since = DateTime.now().subtract(window).toIso8601String();
    return _get('/devices/$id/readings?since=$since',
        (d) => (d as List).map((e) => SensorReading.fromJson(e)).toList());
  }

  Future<PredictionResult> getPrediction(String id) =>
  _get('/predictions/$id', (data) => PredictionResult.fromJson(data));

  Future<List<AlertItem>> getAlerts({bool unreadOnly = false}) =>
      _get('/alerts${unreadOnly ? '?unread=true' : ''}',
          (d) => (d as List).map((e) => AlertItem.fromJson(e)).toList());

  Future<void> markRead(String id) async =>
      _c.patch(Uri.parse('$_base/alerts/$id/read'), headers: _h).timeout(_to);

  Future<void> markAllRead() async =>
      _c.post(Uri.parse('$_base/alerts/mark-all-read'), headers: _h).timeout(_to);

  void dispose() => _c.close();
}