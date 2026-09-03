// ─────────────────────────────────────────────
// services/websocket_service.dart
// ─────────────────────────────────────────────

import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'sensor_data.dart';

enum WsConnectionState { connecting, connected, disconnected, error }

class WebSocketService {
  // URL WebSocket du backend FastAPI.
  // Pour Android emulator, utilise par exemple :
  // flutter run --dart-define=WS_BASE_URL=ws://10.0.2.2:8000/ws
  static const String wsBaseUrl = String.fromEnvironment(
    'WS_BASE_URL',
    defaultValue: 'ws://localhost:8000/ws',
  );

  WebSocketChannel? _channel;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  bool _disposed = false;

  final _connectionStateController =
      StreamController<WsConnectionState>.broadcast();
  final _sensorReadingController =
      StreamController<SensorReading>.broadcast();
  final _alertController = StreamController<AlertModel>.broadcast();
  final _motorStatusController =
      StreamController<Map<String, MotorStatus>>.broadcast();

  Stream<WsConnectionState> get connectionState =>
      _connectionStateController.stream;
  Stream<SensorReading> get sensorReadings => _sensorReadingController.stream;
  Stream<AlertModel> get alerts => _alertController.stream;
  Stream<Map<String, MotorStatus>> get motorStatuses =>
      _motorStatusController.stream;

  WsConnectionState _currentState = WsConnectionState.disconnected;

  // ── Connect ──────────────────────────────────

  void connect({String? motorId}) {
    if (_disposed) return;

    final url = motorId != null
        ? '$wsBaseUrl/motors/$motorId'
        : '$wsBaseUrl/all';

    _updateState(WsConnectionState.connecting);

    try {
      _channel = WebSocketChannel.connect(Uri.parse(url));
      _updateState(WsConnectionState.connected);

      _channel!.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
      );

      _startPing();
    } catch (e) {
      _updateState(WsConnectionState.error);
      _scheduleReconnect(motorId: motorId);
    }
  }

  // ── Message Handler ──────────────────────────

  void _handleMessage(dynamic raw) {
    try {
      final Map<String, dynamic> msg = jsonDecode(raw as String);
      final type = msg['type'] as String;

      switch (type) {
        case 'sensor_reading':
          final reading = SensorReading.fromJson(msg['data']);
          _sensorReadingController.add(reading);

        case 'alert':
          final alert = AlertModel.fromJson(msg['data']);
          _alertController.add(alert);

        case 'motor_status_update':
          final statuses = (msg['data'] as Map<String, dynamic>).map(
            (k, v) => MapEntry(k, MotorStatus.values.byName(v as String)),
          );
          _motorStatusController.add(statuses);

        case 'pong':
          break; // heartbeat OK

        default:
          break;
      }
    } catch (_) {
      // message malformé, on ignore
    }
  }

  // ── Subscribe to specific motor ──────────────

  void subscribeMotor(String motorId) {
    _sendMessage({'type': 'subscribe', 'motor_id': motorId});
  }

  void unsubscribeMotor(String motorId) {
    _sendMessage({'type': 'unsubscribe', 'motor_id': motorId});
  }

  void _sendMessage(Map<String, dynamic> msg) {
    if (_currentState == WsConnectionState.connected) {
      _channel?.sink.add(jsonEncode(msg));
    }
  }

  // ── Ping / Reconnect ─────────────────────────

  void _startPing() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      _sendMessage({'type': 'ping'});
    });
  }

  void _handleError(Object error) {
    _updateState(WsConnectionState.error);
    _scheduleReconnect();
  }

  void _handleDisconnect() {
    _updateState(WsConnectionState.disconnected);
    _scheduleReconnect();
  }

  void _scheduleReconnect({String? motorId}) {
    if (_disposed) return;

    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      connect(motorId: motorId);
    });
  }

  void _updateState(WsConnectionState state) {
    if (_disposed) return;

    _currentState = state;
    _connectionStateController.add(state);
  }

  // ── Dispose ──────────────────────────────────

  void dispose() {
    _disposed = true;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _channel?.sink.close();
    _connectionStateController.close();
    _sensorReadingController.close();
    _alertController.close();
    _motorStatusController.close();
  }
}
