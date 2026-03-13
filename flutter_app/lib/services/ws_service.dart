// lib/services/ws_service.dart

import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/models.dart';

enum WsState { connecting, connected, disconnected, error }

class WsService {
  static const _base = 'ws://localhost:8000/ws';

  WebSocketChannel? _ch;
  Timer? _ping;
  Timer? _retry;
  WsState _state = WsState.disconnected;
  String? _currentDevice;

  final _stateStream   = StreamController<WsState>.broadcast();
  final _readingStream = StreamController<SensorReading>.broadcast();
  final _alertStream   = StreamController<AlertItem>.broadcast();
  final _statusStream  = StreamController<Map<String, DeviceStatus>>.broadcast();

  Stream<WsState>                    get onState   => _stateStream.stream;
  Stream<SensorReading>              get onReading => _readingStream.stream;
  Stream<AlertItem>                  get onAlert   => _alertStream.stream;
  Stream<Map<String, DeviceStatus>>  get onStatus  => _statusStream.stream;

  void connect({String? deviceId}) {
    _currentDevice = deviceId;
    final url = deviceId != null ? '$_base/devices/$deviceId' : '$_base/all';
    _setState(WsState.connecting);
    try {
      _ch = WebSocketChannel.connect(Uri.parse(url));
      _setState(WsState.connected);
      _ch!.stream.listen(_onMsg, onError: _onErr, onDone: _onDone);
      _ping = Timer.periodic(const Duration(seconds: 25), (_) => _send({'type': 'ping'}));
    } catch (_) {
      _setState(WsState.error);
      _scheduleRetry();
    }
  }

  void subscribe(String deviceId) => _send({'type': 'subscribe', 'device_id': deviceId});
  void unsubscribe(String deviceId) => _send({'type': 'unsubscribe', 'device_id': deviceId});

  void _onMsg(dynamic raw) {
    try {
      final msg = jsonDecode(raw as String) as Map<String, dynamic>;
      switch (msg['type']) {
        case 'sensor_reading': _readingStream.add(SensorReading.fromJson(msg['data']));
        case 'alert':          _alertStream.add(AlertItem.fromJson(msg['data']));
        case 'status_update':
          final map = (msg['data'] as Map<String, dynamic>)
              .map((k, v) => MapEntry(k, DeviceStatus.values.byName(v as String)));
          _statusStream.add(map);
      }
    } catch (_) {}
  }

  void _send(Map<String, dynamic> msg) {
    if (_state == WsState.connected) _ch?.sink.add(jsonEncode(msg));
  }

  void _onErr(Object _) { _setState(WsState.error); _scheduleRetry(); }
  void _onDone()        { _setState(WsState.disconnected); _scheduleRetry(); }

  void _scheduleRetry() {
    _retry?.cancel();
    _retry = Timer(const Duration(seconds: 5), () => connect(deviceId: _currentDevice));
  }

  void _setState(WsState s) { _state = s; _stateStream.add(s); }

  void dispose() {
    _ping?.cancel(); _retry?.cancel(); _ch?.sink.close();
    _stateStream.close(); _readingStream.close();
    _alertStream.close(); _statusStream.close();
  }
}