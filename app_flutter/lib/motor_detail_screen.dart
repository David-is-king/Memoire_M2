// ─────────────────────────────────────────────
// screens/motor_detail_screen.dart
// Ecran 3 : Détail machine (Vue d'ensemble / Données / Historique / Infos)
// ─────────────────────────────────────────────

import 'dart:async';
import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'websocket_service.dart';
import 'app_theme.dart';
import 'status_badge.dart';
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
    _tabController = TabController(length: 4, vsync: this);
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
        _tempHistory = history.map((r) => ChartDataPoint(time: r.timestamp, value: r.temperature)).toList();
        _vibHistory = history.map((r) => ChartDataPoint(time: r.timestamp, value: r.vibrationRms)).toList();
        _currentHistory = history.map((r) => ChartDataPoint(time: r.timestamp, value: r.current)).toList();
        _acousticHistory = history.map((r) => ChartDataPoint(time: r.timestamp, value: r.acousticDb)).toList();
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
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: Row(
          children: [
            Expanded(
              child: _motor == null
                  ? const SizedBox()
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_motor!.name,
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: Colors.white)),
                        Text(_motor!.location,
                            style: const TextStyle(fontSize: 11, color: Colors.white70)),
                      ],
                    ),
            ),
          ],
        ),
        actions: [
          if (_motor != null)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: StatusBadge(status: _motor!.status),
            ),
          const Icon(Icons.more_vert_rounded, color: Colors.white),
          const SizedBox(width: 8),
        ],
        bottom: TabBar(
          controller: _tabController,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          labelStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
          tabs: const [
            Tab(text: 'Vue d\'ensemble'),
            Tab(text: 'Données'),
            Tab(text: 'Historique'),
            Tab(text: 'Infos'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppTheme.primary))
          : TabBarView(
              controller: _tabController,
              children: [
                _buildOverviewTab(),
                _buildDataTab(),
                _buildHistoryTab(),
                _buildInfoTab(),
              ],
            ),
    );
  }

  // ── Tab 1: Vue d'ensemble ─────────────────────

  Widget _buildOverviewTab() {
    if (_motor == null) return const SizedBox();
    final r = _motor!.lastReading;
    final prob = _motor!.failureProbability;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Center(
          child: HealthGauge(
            healthScore: _motor!.healthScore,
            failureProbability: prob,
            rulDays: _motor!.estimatedRulDays,
            size: 190,
          ),
        ),
        const SizedBox(height: 24),
        if (r != null)
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppTheme.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppTheme.border),
            ),
            child: Column(
              children: [
                _InfoLine(label: 'Vibration', value: '${r.vibrationRms.toStringAsFixed(1)} mm/s',
                    severity: r.vibrationRms > 5 ? 2 : r.vibrationRms > 3 ? 1 : 0),
                const Divider(color: AppTheme.border, height: 20),
                _InfoLine(label: 'Température', value: '${r.temperature.toStringAsFixed(0)} °C',
                    severity: r.temperature > 85 ? 2 : r.temperature > 70 ? 1 : 0),
                const Divider(color: AppTheme.border, height: 20),
                _InfoLine(label: 'Pression', value: '${(r.voltage * 0.78).toStringAsFixed(0)} bar', severity: 1),
                const Divider(color: AppTheme.border, height: 20),
                _InfoLine(label: 'Courant', value: '${r.current.toStringAsFixed(0)} A', severity: 0),
              ],
            ),
          ),
        const SizedBox(height: 20),
        const Text('Évolution du risque', style: AppTextStyles.headingSmall),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppTheme.border),
          ),
          child: RealtimeChart(
            dataPoints: _vibHistory,
            label: 'Risque de panne',
            unit: '%',
            color: AppTheme.danger,
            minY: 0,
            maxY: 15,
            height: 140,
          ),
        ),
      ],
    );
  }

  // ── Tab 2: Données (capteurs temps réel) ──────

  Widget _buildDataTab() {
    if (_motor == null) return const SizedBox();
    final r = _motor!.lastReading;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        if (r != null)
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 1.6,
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
                valueColor: r.acousticDb > 85 ? AppTheme.danger : AppTheme.primary,
                isAlert: r.acousticDb > 85,
              ),
            ],
          ),
        const SizedBox(height: 24),
        _chartCard('Température', '°C', AppTheme.warning, _tempHistory, 20, 120),
        const SizedBox(height: 20),
        _chartCard('Vibration RMS', 'm/s²', AppTheme.primary, _vibHistory, 0, 15),
        const SizedBox(height: 20),
        _chartCard('Courant', 'A', AppTheme.success, _currentHistory, 0, 30),
        const SizedBox(height: 20),
        _chartCard('Acoustique', 'dB', const Color(0xFF7C4DFF), _acousticHistory, 40, 100),
      ],
    );
  }

  Widget _chartCard(String label, String unit, Color color, List<ChartDataPoint> data, double minY, double maxY) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppTheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTheme.border),
      ),
      child: RealtimeChart(
        dataPoints: data, label: label, unit: unit, color: color,
        minY: minY, maxY: maxY, height: 130,
      ),
    );
  }

  // ── Tab 3: Historique ────────────────────────

  Widget _buildHistoryTab() {
    if (_prediction == null) {
      return const Center(child: Text('Historique indisponible', style: AppTextStyles.labelMono));
    }
    final p = _prediction!;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _HistoryEntry(
          dateLabel: _formatDate(p.predictedAt),
          title: 'Analyse de prédiction',
          subtitle: p.maintenanceRecommendation,
          color: p.failureProbability > 0.7 ? AppTheme.danger
              : p.failureProbability > 0.4 ? AppTheme.warning : AppTheme.success,
          icon: p.failureProbability > 0.7 ? Icons.error_rounded
              : p.failureProbability > 0.4 ? Icons.warning_rounded : Icons.check_circle_rounded,
        ),
        ...p.anomalyFeatures.map((f) => _HistoryEntry(
              dateLabel: _formatDate(p.predictedAt),
              title: 'Anomalie détectée',
              subtitle: f,
              color: AppTheme.warning,
              icon: Icons.report_problem_rounded,
            )),
      ],
    );
  }

  // ── Tab 4: Infos ─────────────────────────────

  Widget _buildInfoTab() {
    if (_motor == null) return const SizedBox();
    final m = _motor!;

    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: AppTheme.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: AppTheme.border),
          ),
          child: Column(
            children: [
              _InfoLine(label: 'ID Machine', value: m.id, severity: -1),
              const Divider(color: AppTheme.border, height: 20),
              _InfoLine(label: 'Emplacement', value: m.location, severity: -1),
              const Divider(color: AppTheme.border, height: 20),
              _InfoLine(label: 'Statut', value: _statusLabel(m.status), severity: -1),
              const Divider(color: AppTheme.border, height: 20),
              _InfoLine(label: 'RUL estimé', value: '${m.estimatedRulDays} jours', severity: -1),
              const Divider(color: AppTheme.border, height: 20),
              _InfoLine(label: 'Dernière mise à jour', value: _formatDate(m.lastSeen), severity: -1),
            ],
          ),
        ),
      ],
    );
  }

  String _statusLabel(MotorStatus s) => switch (s) {
        MotorStatus.healthy => 'En fonctionnement',
        MotorStatus.warning => 'Attention requise',
        MotorStatus.critical => 'Critique',
        MotorStatus.offline => 'Hors ligne',
      };

  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}/'
        '${dt.month.toString().padLeft(2, '0')}/'
        '${dt.year} ${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }
}

class _InfoLine extends StatelessWidget {
  final String label;
  final String value;
  final int severity; // -1 = neutre, 0 = normal, 1 = majeur, 2 = critique

  const _InfoLine({required this.label, required this.value, required this.severity});

  @override
  Widget build(BuildContext context) {
    Color? badgeColor;
    String? badgeLabel;
    if (severity == 2) { badgeColor = AppTheme.danger; badgeLabel = 'Critique'; }
    if (severity == 1) { badgeColor = AppTheme.warning; badgeLabel = 'Majeur'; }
    if (severity == 0) { badgeColor = AppTheme.success; badgeLabel = 'Normal'; }

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: AppTextStyles.bodyText),
        Row(
          children: [
            Text(value, style: AppTextStyles.headingSmall),
            if (badgeColor != null) ...[
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: badgeColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(badgeLabel!, style: TextStyle(color: badgeColor, fontSize: 10, fontWeight: FontWeight.w700)),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

class _HistoryEntry extends StatelessWidget {
  final String dateLabel;
  final String title;
  final String subtitle;
  final Color color;
  final IconData icon;

  const _HistoryEntry({
    required this.dateLabel,
    required this.title,
    required this.subtitle,
    required this.color,
    required this.icon,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(dateLabel, style: AppTextStyles.labelMono.copyWith(fontSize: 10)),
                const SizedBox(height: 4),
                Text(title, style: AppTextStyles.headingSmall),
                const SizedBox(height: 2),
                Text(subtitle, style: AppTextStyles.bodyText),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
