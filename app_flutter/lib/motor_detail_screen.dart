// ─────────────────────────────────────────────
// screens/motor_detail_screen.dart
// ─────────────────────────────────────────────

import 'dart:async';
import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'websocket_service.dart';
import 'app_theme.dart';
import 'sensor_card.dart';
import 'realtime_chart.dart';

class MotorDetailScreen extends StatefulWidget {
  final String motorId;
  const MotorDetailScreen({super.key, required this.motorId});

  @override
  State<MotorDetailScreen> createState() => _MotorDetailScreenState();
}

class _MotorDetailScreenState extends State<MotorDetailScreen>
    with SingleTickerProviderStateMixin {
  final _api = ApiService();
  final _ws = WebSocketService();
  late TabController _tabController;

  MotorDevice? _motor;
  PredictionResult? _prediction;
  List<ChartDataPoint> _tempHistory = [];
  List<ChartDataPoint> _vibHistory = [];
  List<ChartDataPoint> _currentHistory = [];
  List<ChartDataPoint> _acousticHistory = [];

  late StreamSubscription _readingSub;
  bool _loading = true;

  static const int _maxHistoryPoints = 60;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _loadData();
    _connectWs();
  }

  Future<void> _loadData() async {
    try {
      final motor = await _api.getMotorById(widget.motorId);
      final prediction = await _api.getPrediction(widget.motorId);
      final history = await _api.getSensorHistory(
        widget.motorId,
        window: const Duration(hours: 1),
      );

      setState(() {
        _motor = motor;
        _prediction = prediction;
        _tempHistory = history
            .map((r) => ChartDataPoint(time: r.timestamp, value: r.temperature))
            .toList();
        _vibHistory = history
            .map((r) =>
                ChartDataPoint(time: r.timestamp, value: r.vibrationRms))
            .toList();
        _currentHistory = history
            .map((r) => ChartDataPoint(time: r.timestamp, value: r.current))
            .toList();
        _acousticHistory = history
            .map((r) => ChartDataPoint(time: r.timestamp, value: r.acousticDb))
            .toList();
        _loading = false;
      });
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  void _connectWs() {
    _ws.connect(motorId: widget.motorId);
    _readingSub = _ws.sensorReadings.listen((reading) {
      setState(() {
        void addPoint(List<ChartDataPoint> list, double val) {
          list.add(ChartDataPoint(time: reading.timestamp, value: val));
          if (list.length > _maxHistoryPoints) list.removeAt(0);
        }

        addPoint(_tempHistory, reading.temperature);
        addPoint(_vibHistory, reading.vibrationRms);
        addPoint(_currentHistory, reading.current);
        addPoint(_acousticHistory, reading.acousticDb);

        // Update lastReading in motor
        if (_motor != null) {
          _motor = MotorDevice(
            id: _motor!.id,
            name: _motor!.name,
            location: _motor!.location,
            status: _motor!.status,
            healthScore: _motor!.healthScore,
            failureProbability: _motor!.failureProbability,
            estimatedRulDays: _motor!.estimatedRulDays,
            lastReading: reading,
            lastSeen: DateTime.now(),
          );
        }
      });
    });
  }

  @override
  void dispose() {
    _readingSub.cancel();
    _ws.dispose();
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: AppTheme.background,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded,
              color: AppTheme.textSecondary, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: _motor == null
            ? const SizedBox()
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _motor!.name,
                    style: AppTextStyles.headingMedium.copyWith(fontSize: 16),
                  ),
                  Text(
                    _motor!.location.toUpperCase(),
                    style: AppTextStyles.labelMono,
                  ),
                ],
              ),
        actions: [
          if (_motor != null)
            Padding(
              padding: const EdgeInsets.only(right: 16),
              child: StatusBadge(status: _motor!.status),
            ),
        ],
        bottom: TabBar(
          controller: _tabController,
          labelColor: AppTheme.primary,
          unselectedLabelColor: AppTheme.textMuted,
          indicatorColor: AppTheme.primary,
          indicatorSize: TabBarIndicatorSize.label,
          labelStyle:
              AppTextStyles.labelMono.copyWith(color: AppTheme.primary),
          unselectedLabelStyle: AppTextStyles.labelMono,
          tabs: const [
            Tab(text: 'VUE GÉNÉRALE'),
            Tab(text: 'CAPTEURS'),
            Tab(text: 'PRÉDICTION'),
          ],
        ),
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AppTheme.primary))
          : TabBarView(
              controller: _tabController,
              children: [
                _buildOverviewTab(),
                _buildSensorsTab(),
                _buildPredictionTab(),
              ],
            ),
    );
  }

  // ── Tab 1: Vue générale ──────────────────────

  Widget _buildOverviewTab() {
    if (_motor == null) return const SizedBox();
    final r = _motor!.lastReading;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        // Gauge centrale
        Center(
          child: HealthGauge(
            healthScore: _motor!.healthScore,
            failureProbability: _motor!.failureProbability,
            rulDays: _motor!.estimatedRulDays,
            size: 200,
          ),
        ),
        const SizedBox(height: 28),

        // Sensor cards
        if (r != null)
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 1.8,
            children: [
              SensorCard(
                label: 'Température',
                value: r.temperature.toStringAsFixed(1),
                unit: '°C',
                icon: Icons.thermostat_rounded,
                valueColor: r.temperature > 85 ? AppTheme.danger : AppTheme.primary,
                isAlert: r.temperature > 85,
              ),
              SensorCard(
                label: 'Vibration RMS',
                value: r.vibrationRms.toStringAsFixed(2),
                unit: 'm/s²',
                icon: Icons.vibration_rounded,
                valueColor: r.vibrationRms > 5 ? AppTheme.danger : AppTheme.primary,
                isAlert: r.vibrationRms > 5,
              ),
              SensorCard(
                label: 'Courant',
                value: r.current.toStringAsFixed(1),
                unit: 'A',
                icon: Icons.electric_bolt_rounded,
                valueColor: AppTheme.warning,
              ),
              SensorCard(
                label: 'Acoustique',
                value: r.acousticDb.toStringAsFixed(0),
                unit: 'dB',
                icon: Icons.graphic_eq_rounded,
                valueColor:
                    r.acousticDb > 85 ? AppTheme.danger : AppTheme.primary,
                isAlert: r.acousticDb > 85,
              ),
            ],
          ),
      ],
    );
  }

  // ── Tab 2: Capteurs temps réel ───────────────

  Widget _buildSensorsTab() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _ChartSection(
          label: 'Température',
          unit: '°C',
          color: AppTheme.warning,
          data: _tempHistory,
          minY: 20,
          maxY: 120,
        ),
        const SizedBox(height: 24),
        _ChartSection(
          label: 'Vibration RMS',
          unit: 'm/s²',
          color: AppTheme.primary,
          data: _vibHistory,
          minY: 0,
          maxY: 15,
        ),
        const SizedBox(height: 24),
        _ChartSection(
          label: 'Courant',
          unit: 'A',
          color: AppTheme.accent,
          data: _currentHistory,
          minY: 0,
          maxY: 30,
        ),
        const SizedBox(height: 24),
        _ChartSection(
          label: 'Acoustique',
          unit: 'dB',
          color: const Color(0xFFB060FF),
          data: _acousticHistory,
          minY: 40,
          maxY: 100,
        ),
      ],
    );
  }

  // ── Tab 3: Prédiction ML ─────────────────────

  Widget _buildPredictionTab() {
    if (_prediction == null) {
      return const Center(
          child: Text('Aucune prédiction disponible',
              style: AppTextStyles.labelMono));
    }

    final p = _prediction!;
    final prob = p.failureProbability;
    final probColor = prob > 0.7
        ? AppTheme.danger
        : prob > 0.4
            ? AppTheme.warning
            : AppTheme.accent;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        // Score principal
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: probColor.withValues(alpha: 0.3)),
          ),
          child: Column(
            children: [
              Text(
                'PROBABILITÉ DE PANNE',
                style: AppTextStyles.labelMono,
              ),
              const SizedBox(height: 12),
              Text(
                '${(prob * 100).toInt()}%',
                style: TextStyle(
                  fontSize: 56,
                  fontWeight: FontWeight.w900,
                  color: probColor,
                  fontFamily: 'Courier',
                  letterSpacing: -2,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'DURÉE DE VIE RESTANTE : ${p.estimatedRulDays} JOURS',
                style: AppTextStyles.labelMono.copyWith(
                  color: AppTheme.textPrimary,
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // Recommandation
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'RECOMMANDATION',
                style: AppTextStyles.labelMono,
              ),
              const SizedBox(height: 8),
              Text(
                p.maintenanceRecommendation,
                style: const TextStyle(
                  color: AppTheme.textPrimary,
                  fontSize: 14,
                  height: 1.5,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // Anomalies détectées
        if (p.anomalyFeatures.isNotEmpty)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.dangerDim,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppTheme.danger.withValues(alpha: 0.3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.warning_amber_rounded,
                        color: AppTheme.danger, size: 14),
                    const SizedBox(width: 6),
                    Text(
                      'ANOMALIES DÉTECTÉES',
                      style: AppTextStyles.labelMono.copyWith(
                        color: AppTheme.danger,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                ...p.anomalyFeatures.map(
                  (f) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      children: [
                        const Icon(Icons.chevron_right,
                            color: AppTheme.danger, size: 12),
                        const SizedBox(width: 6),
                        Text(
                          f,
                          style: AppTextStyles.labelMono.copyWith(
                            color: AppTheme.textPrimary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),

        const SizedBox(height: 16),

        // Timestamp
        Text(
          'ANALYSE DU ${_formatDate(p.predictedAt)}',
          style: AppTextStyles.labelMono,
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}/'
        '${dt.month.toString().padLeft(2, '0')}/'
        '${dt.year} ${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }
}

class _ChartSection extends StatelessWidget {
  final String label;
  final String unit;
  final Color color;
  final List<ChartDataPoint> data;
  final double? minY;
  final double? maxY;

  const _ChartSection({
    required this.label,
    required this.unit,
    required this.color,
    required this.data,
    this.minY,
    this.maxY,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTheme.border),
      ),
      child: RealtimeChart(
        dataPoints: data,
        label: label,
        unit: unit,
        color: color,
        minY: minY,
        maxY: maxY,
        height: 130,
      ),
    );
  }
}
