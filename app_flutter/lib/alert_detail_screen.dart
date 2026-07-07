// Détail d'une alerte

import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'app_theme.dart';
import 'status_badge.dart';
import 'motor_detail_screen.dart';

class AlertDetailScreen extends StatefulWidget {
  final AlertModel alert;
  const AlertDetailScreen({super.key, required this.alert});

  @override
  State<AlertDetailScreen> createState() => _AlertDetailScreenState();
}

class _AlertDetailScreenState extends State<AlertDetailScreen> {
  final _api = ApiService();
  MotorDevice? _motor;
  PredictionResult? _prediction;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final motor = await _api.getMotorById(widget.alert.motorId);
      PredictionResult? pred;
      try {
        pred = await _api.getPrediction(widget.alert.motorId);
      } catch (_) {}
      if (mounted) setState(() { _motor = motor; _prediction = pred; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  (Color, IconData) get _severityStyle => switch (widget.alert.severity) {
        AlertSeverity.critical => (AppTheme.danger, Icons.crisis_alert_rounded),
        AlertSeverity.warning => (AppTheme.warning, Icons.warning_amber_rounded),
        AlertSeverity.info => (AppTheme.primary, Icons.info_outline_rounded),
      };

  @override
  Widget build(BuildContext context) {
    final (color, icon) = _severityStyle;
    final r = _motor?.lastReading;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: color,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('Détail alerte'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppTheme.primary))
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(10)),
                      child: Icon(icon, color: color, size: 22),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(widget.alert.motorName, style: AppTextStyles.headingMedium),
                          if (_motor != null) Text(_motor!.location, style: AppTextStyles.labelMono),
                        ],
                      ),
                    ),
                    if (_motor != null) StatusBadge(status: _motor!.status),
                  ],
                ),
                const SizedBox(height: 20),
                Text(widget.alert.title, style: AppTextStyles.headingMedium),
                const SizedBox(height: 4),
                Text('Détectée le : ${_formatDate(widget.alert.createdAt)}', style: AppTextStyles.labelMono),
                const SizedBox(height: 20),
                const Text('Description', style: AppTextStyles.headingSmall),
                const SizedBox(height: 8),
                Text(widget.alert.message, style: AppTextStyles.bodyText),
                const SizedBox(height: 24),

                if (r != null) ...[
                  const Text('Mesures', style: AppTextStyles.headingSmall),
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: AppTheme.surface,
                      borderRadius: BorderRadius.circular(14),
                      border: Border.all(color: AppTheme.border),
                    ),
                    child: Column(
                      children: [
                        _MeasureLine(icon: Icons.vibration_rounded, label: 'Vibration', value: '${r.vibrationRms.toStringAsFixed(1)} mm/s', severity: r.vibrationRms > 5 ? 2 : r.vibrationRms > 3 ? 1 : 0),
                        const Divider(color: AppTheme.border, height: 18),
                        _MeasureLine(icon: Icons.thermostat_rounded, label: 'Température', value: '${r.temperature.toStringAsFixed(0)} °C', severity: r.temperature > 85 ? 2 : r.temperature > 70 ? 1 : 0),
                        const Divider(color: AppTheme.border, height: 18),
                        _MeasureLine(icon: Icons.speed_rounded, label: 'Pression', value: '${(r.voltage * 0.78).toStringAsFixed(0)} bar', severity: 1),
                        const Divider(color: AppTheme.border, height: 18),
                        _MeasureLine(icon: Icons.electric_bolt_rounded, label: 'Courant', value: '${r.current.toStringAsFixed(0)} A', severity: 0),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                ],

                const Text('Actions recommandées', style: AppTextStyles.headingSmall),
                const SizedBox(height: 8),
                Text(
                  _prediction?.maintenanceRecommendation ??
                      'Planifier une intervention pour vérifier l\'état de la machine.',
                  style: AppTextStyles.bodyText,
                ),
                const SizedBox(height: 20),

                SizedBox(
                  width: double.infinity,
                  height: 50,
                  child: ElevatedButton(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => MotorDetailScreen(motorId: widget.alert.motorId)),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: color,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: const Text('Intervention immédiate',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                  ),
                ),
                const SizedBox(height: 12),
                SizedBox(
                  width: double.infinity,
                  height: 50,
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: AppTheme.border),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    ),
                    child: const Text('Planifier plus tard',
                        style: TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.w600)),
                  ),
                ),
              ],
            ),
    );
  }

  String _formatDate(DateTime dt) {
    return '${dt.day.toString().padLeft(2, '0')}/'
        '${dt.month.toString().padLeft(2, '0')}/'
        '${dt.year} ${dt.hour.toString().padLeft(2, '0')}:'
        '${dt.minute.toString().padLeft(2, '0')}';
  }
}

class _MeasureLine extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final int severity;

  const _MeasureLine({required this.icon, required this.label, required this.value, required this.severity});

  @override
  Widget build(BuildContext context) {
    final (badgeColor, badgeLabel) = switch (severity) {
      2 => (AppTheme.danger, 'Critique'),
      1 => (AppTheme.warning, 'Majeur'),
      _ => (AppTheme.success, 'Normal'),
    };

    return Row(
      children: [
        Icon(icon, size: 16, color: AppTheme.textSecondary),
        const SizedBox(width: 10),
        Expanded(child: Text(label, style: AppTextStyles.bodyText)),
        Text(value, style: AppTextStyles.headingSmall),
        const SizedBox(width: 8),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(color: badgeColor.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
          child: Text(badgeLabel, style: TextStyle(color: badgeColor, fontSize: 10, fontWeight: FontWeight.w700)),
        ),
      ],
    );
  }
}
