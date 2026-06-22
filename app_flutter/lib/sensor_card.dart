// ─────────────────────────────────────────────
// widgets/sensor_card.dart + health_gauge.dart
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'app_theme.dart';

class SensorCard extends StatelessWidget {
  final String label;
  final String value;
  final String unit;
  final IconData icon;
  final Color? valueColor;
  final bool isAlert;

  const SensorCard({
    super.key,
    required this.label,
    required this.value,
    required this.unit,
    required this.icon,
    this.valueColor,
    this.isAlert = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = valueColor ?? AppTheme.primary;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: isAlert ? AppTheme.dangerBg : AppTheme.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isAlert ? AppTheme.danger.withValues(alpha: 0.4) : AppTheme.border,
          width: isAlert ? 1.5 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 16),
              const SizedBox(width: 6),
              Expanded(
                child: Text(label, style: AppTextStyles.labelMono, overflow: TextOverflow.ellipsis),
              ),
              if (isAlert)
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(color: AppTheme.danger, shape: BoxShape.circle),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(value, style: AppTextStyles.valueSmall.copyWith(color: color)),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(
                  unit,
                  style: AppTextStyles.labelMono.copyWith(color: color.withValues(alpha: 0.7), fontSize: 10),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Gauge circulaire de santé, comme sur l'écran "Détail machine".
class HealthGauge extends StatelessWidget {
  final double healthScore;
  final double failureProbability;
  final int rulDays;
  final double size;

  const HealthGauge({
    super.key,
    required this.healthScore,
    required this.failureProbability,
    required this.rulDays,
    this.size = 180,
  });

  Color get _gaugeColor {
    if (healthScore >= 0.75) return AppTheme.success;
    if (healthScore >= 0.50) return AppTheme.warning;
    return AppTheme.danger;
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          CustomPaint(
            size: Size(size, size),
            painter: _GaugePainter(value: healthScore, color: _gaugeColor),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${(healthScore * 100).toInt()}%',
                style: TextStyle(
                  fontSize: size * 0.22,
                  fontWeight: FontWeight.w800,
                  color: _gaugeColor,
                  letterSpacing: -1,
                ),
              ),
              Text('Santé', style: AppTextStyles.labelMono.copyWith(fontSize: 10)),
              const SizedBox(height: 4),
              Text(
                failureProbability >= 0.7 ? 'Risque très élevé'
                    : failureProbability >= 0.4 ? 'Risque élevé'
                    : 'Risque faible',
                style: TextStyle(color: _gaugeColor, fontSize: 11, fontWeight: FontWeight.w700),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _GaugePainter extends CustomPainter {
  final double value;
  final Color color;

  _GaugePainter({required this.value, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2 - 12;
    const startAngle = 2.35;
    const sweepTotal = 4.71;

    final trackPaint = Paint()
      ..color = AppTheme.border
      ..strokeWidth = 10
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), startAngle, sweepTotal, false, trackPaint);

    final progressPaint = Paint()
      ..color = color
      ..strokeWidth = 10
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(Rect.fromCircle(center: center, radius: radius), startAngle, sweepTotal * value, false, progressPaint);
  }

  @override
  bool shouldRepaint(_GaugePainter old) => old.value != value || old.color != color;
}
