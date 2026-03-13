// lib/screens/device_detail_screen.dart

import 'dart:async';
import 'package:flutter/material.dart';
import '../models/models.dart';
import '../services/api_service.dart';
import '../services/ws_service.dart';
import '../theme/app_theme.dart';
import '../widgets/shared_widgets.dart';
import '../widgets/health_gauge.dart';
import '../widgets/sensor_chart.dart';

class DeviceDetailScreen extends StatefulWidget {
  final String deviceId;
  const DeviceDetailScreen({super.key, required this.deviceId});
  @override
  State<DeviceDetailScreen> createState() => _DeviceDetailScreenState();
}

class _DeviceDetailScreenState extends State<DeviceDetailScreen> {
  final _api = ApiService();
  final _ws  = WsService();

  MotorDevice? _device;
  PredictionResult? _prediction;
  bool _loadingPred = false;

  final _tempPts    = <ChartPoint>[];
  final _vibPts     = <ChartPoint>[];
  final _powerPts   = <ChartPoint>[];
  int _chartTab = 0;

  late StreamSubscription _readingSub;
  static const _maxPts = 50;

  @override
  void initState() {
    super.initState();
    _loadDevice();
    _loadHistory();
    _ws.connect(deviceId: widget.deviceId);
    _readingSub = _ws.onReading.listen(_onReading);
  }

  Future<void> _loadDevice() async {
    try {
      final d = await _api.getDevice(widget.deviceId);
      if (mounted) setState(() => _device = d);
    } catch (_) {}
  }

  Future<void> _loadHistory() async {
    try {
      final hist = await _api.getHistory(widget.deviceId, window: const Duration(hours: 24));
      if (!mounted) return;
      setState(() {
        for (final r in hist) {
          _tempPts.add(ChartPoint(time: r.timestamp, value: r.temperature));
          _vibPts.add(ChartPoint(time: r.timestamp, value: r.vibration));
          _powerPts.add(ChartPoint(time: r.timestamp, value: r.current * r.voltage / 1000));
        }
      });
    } catch (_) {}
  }

  void _onReading(SensorReading r) {
    setState(() {
      void add(List<ChartPoint> list, double v) {
        list.add(ChartPoint(time: r.timestamp, value: v));
        if (list.length > _maxPts) list.removeAt(0);
      }
      add(_tempPts, r.temperature);
      add(_vibPts, r.vibration);
      add(_powerPts, r.current * r.voltage / 1000);
      if (_device != null) {
        _device = MotorDevice(
          id: _device!.id, name: _device!.name, location: _device!.location,
          status: _device!.status, healthScore: _device!.healthScore,
          failureProb: _device!.failureProb, rulDays: _device!.rulDays,
          lastReading: r, lastSeen: DateTime.now(), isActive: _device!.isActive,
        );
      }
    });
  }

  Future<void> _predictFailure() async {
    setState(() => _loadingPred = true);
    try {
      final p = await _api.getPrediction(widget.deviceId);
      if (mounted) setState(() { _prediction = p; _loadingPred = false; });
      _showPredictionSheet();
    } catch (_) {
      if (mounted) setState(() => _loadingPred = false);
    }
  }

  void _showPredictionSheet() {
    if (_prediction == null) return;
    final p = _prediction!;
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _PredictionSheet(prediction: p),
    );
  }

  @override
  void dispose() {
    _readingSub.cancel(); _ws.dispose(); _api.dispose();
    super.dispose();
  }

  List<ChartPoint> get _currentChartData =>
      [_tempPts, _vibPts, _powerPts][_chartTab];

  (double?, double?) get _chartBounds => switch (_chartTab) {
    0 => (20.0, 120.0),
    1 => (0.0, 15.0),
    _ => (0.0, null),
  };

  @override
  Widget build(BuildContext context) {
    final r = _device?.lastReading;
    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(
        title: Text(_device?.name ?? 'Device', style: AppText.h3),
        actions: [
          if (_device != null) Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(child: StatusBadge(status: _device!.status)),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [

          // ── Health Score Card ──
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(20),
              boxShadow: cardShadow(),
            ),
            child: Column(children: [
              const Text('Health Score', style: AppText.h2),
              const SizedBox(height: 16),
              HealthGauge(score: _device?.healthScore ?? 0, size: 220),
            ]),
          ),

          const SizedBox(height: 16),

          // ── 4 Sensor Metrics ──
          if (r != null)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 8),
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(20),
                boxShadow: cardShadow(),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                children: [
                  SensorMetricTile(icon: Icons.thermostat_rounded, label: 'Temp.',
                      value: '${r.temperature.toStringAsFixed(0)}°C',
                      isAlert: r.temperature > 85),
                  _divider(),
                  SensorMetricTile(icon: Icons.vibration_rounded, label: 'Vibration',
                      value: '${r.vibration.toStringAsFixed(1)} g',
                      isAlert: r.vibration > 5),
                  _divider(),
                  SensorMetricTile(icon: Icons.electric_bolt_rounded, label: 'Power',
                      value: '${r.voltage.toStringAsFixed(0)} V'),
                  _divider(),
                  SensorMetricTile(icon: Icons.speed_rounded, label: 'Speed',
                      value: '${r.speedRpm.toStringAsFixed(0)} rpm'),
                ],
              ),
            ),

          const SizedBox(height: 16),

          // ── Chart ──
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(20),
              boxShadow: cardShadow(),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Last 24 Hours', style: AppText.h2),
              const SizedBox(height: 14),
              ChartTabSelector(
                tabs: const ['Temperature', 'Vibration', 'Power'],
                selectedIndex: _chartTab,
                onChanged: (i) => setState(() => _chartTab = i),
              ),
              const SizedBox(height: 16),
              SensorChart(
                points: _currentChartData,
                color: [AppColors.primary, AppColors.warning, AppColors.info][_chartTab],
                minY: _chartBounds.$1,
                maxY: _chartBounds.$2,
              ),
            ]),
          ),

          const SizedBox(height: 20),

          // ── Predict Failure Button ──
          PrimaryButton(
            label: 'Predict Failure',
            icon: Icons.play_arrow_rounded,
            loading: _loadingPred,
            onTap: _predictFailure,
          ),

          const SizedBox(height: 8),
        ]),
      ),
    );
  }

  Widget _divider() => Container(height: 36, width: 1, color: AppColors.border);
}

// ── Prediction Bottom Sheet ───────────────────────────────
class _PredictionSheet extends StatelessWidget {
  final PredictionResult prediction;
  const _PredictionSheet({required this.prediction});

  @override
  Widget build(BuildContext context) {
    final p = prediction;
    final prob = (p.failureProb * 100).toInt();
    final probColor = prob >= 70 ? AppColors.critical : prob >= 40 ? AppColors.warning : AppColors.healthy;

    return Container(
      margin: EdgeInsets.only(top: MediaQuery.of(context).size.height * 0.3),
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      decoration: const BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
          // Handle
          Center(child: Container(width: 40, height: 4,
              decoration: BoxDecoration(color: AppColors.border, borderRadius: BorderRadius.circular(2)))),
          const SizedBox(height: 20),

          Row(children: [
            const Text('Failure Prediction', style: AppText.h2),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              decoration: BoxDecoration(
                color: probColor.withOpacity(0.1),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text('$prob% risk', style: TextStyle(
                fontFamily: 'Nunito', fontSize: 14, fontWeight: FontWeight.w800,
                color: probColor,
              )),
            ),
          ]),
          const SizedBox(height: 6),
          Text('RUL: ${p.rulDays} days remaining', style: AppText.body),
          const SizedBox(height: 16),

          // Recommendation
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.primaryLight,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.primaryMid),
            ),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.lightbulb_outline_rounded, color: AppColors.primary, size: 18),
              const SizedBox(width: 10),
              Expanded(child: Text(p.recommendation,
                  style: AppText.body.copyWith(color: AppColors.textDark))),
            ]),
          ),

          if (p.anomalies.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Text('Detected Anomalies', style: AppText.h3),
            const SizedBox(height: 8),
            ...p.anomalies.map((a) => Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                Container(width: 6, height: 6, decoration: const BoxDecoration(
                    color: AppColors.critical, shape: BoxShape.circle)),
                const SizedBox(width: 8),
                Expanded(child: Text(a, style: AppText.body)),
              ]),
            )),
          ],

          const SizedBox(height: 20),
          PrimaryButton(label: 'Schedule Maintenance', icon: Icons.calendar_today_rounded,
              onTap: () => Navigator.pop(context)),
        ]),
      ),
    );
  }
}