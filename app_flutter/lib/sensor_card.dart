// ─────────────────────────────────────────────
// widgets/sensor_card.dart
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'app_theme.dart';
import 'sensor_data.dart';

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

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isAlert
            ? AppTheme.dangerDim
            : AppTheme.surfaceElevated,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isAlert ? AppTheme.danger : AppTheme.border,
          width: isAlert ? 1.5 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 14),
              const SizedBox(width: 6),
              Text(
                label.toUpperCase(),
                style: AppTextStyles.labelMono,
              ),
              if (isAlert) ...[
                const Spacer(),
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: AppTheme.danger,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: 12),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                value,
                style: AppTextStyles.valueSmall.copyWith(color: color),
              ),
              const SizedBox(width: 4),
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(
                  unit,
                  style: AppTextStyles.labelMono.copyWith(
                    color: color.withValues(alpha: 0.6),
                    fontSize: 10,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}


// ─────────────────────────────────────────────
// widgets/health_gauge.dart
// ─────────────────────────────────────────────

class HealthGauge extends StatelessWidget {
  final double healthScore; // 0.0 → 1.0
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
    if (healthScore >= 0.75) return AppTheme.accent;
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
            painter: _GaugePainter(
              value: healthScore,
              color: _gaugeColor,
            ),
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
                  fontFamily: 'Courier',
                  letterSpacing: -1,
                ),
              ),
              Text(
                'SANTÉ',
                style: AppTextStyles.labelMono.copyWith(fontSize: 9),
              ),
              const SizedBox(height: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppTheme.surface,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: AppTheme.border),
                ),
                child: Text(
                  'RUL: $rulDays j',
                  style: AppTextStyles.labelMono.copyWith(
                    color: AppTheme.textPrimary,
                    fontSize: 9,
                  ),
                ),
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
    const startAngle = 2.35; // ~135°
    const sweepTotal = 4.71; // ~270°

    // Track
    final trackPaint = Paint()
      ..color = AppTheme.border
      ..strokeWidth = 10
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepTotal,
      false,
      trackPaint,
    );

    // Progress
    final progressPaint = Paint()
      ..color = color
      ..strokeWidth = 10
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepTotal * value,
      false,
      progressPaint,
    );

    // Glow
    final glowPaint = Paint()
      ..color = color.withValues(alpha: 0.2)
      ..strokeWidth = 18
      ..style = PaintingStyle.stroke
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6);

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepTotal * value,
      false,
      glowPaint,
    );
  }

  @override
  bool shouldRepaint(_GaugePainter old) =>
      old.value != value || old.color != color;
}


// ─────────────────────────────────────────────
// widgets/status_badge.dart
// ─────────────────────────────────────────────

class StatusBadge extends StatefulWidget {
  final MotorStatus status;
  final bool animate;

  const StatusBadge({
    super.key,
    required this.status,
    this.animate = true,
  });

  @override
  State<StatusBadge> createState() => _StatusBadgeState();
}

class _StatusBadgeState extends State<StatusBadge>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _pulse = Tween<double>(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );

    if (widget.animate &&
        (widget.status == MotorStatus.critical ||
            widget.status == MotorStatus.warning)) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  (Color, Color, String) get _config => switch (widget.status) {
    MotorStatus.healthy => (AppTheme.accent, AppTheme.accentDim, 'OPÉRATIONNEL'),
    MotorStatus.warning => (AppTheme.warning, AppTheme.warningDim, 'ATTENTION'),
    MotorStatus.critical => (AppTheme.danger, AppTheme.dangerDim, 'CRITIQUE'),
    MotorStatus.offline => (AppTheme.textMuted, AppTheme.surface, 'HORS LIGNE'),
  };

  @override
  Widget build(BuildContext context) {
    final (fg, bg, label) = _config;

    return AnimatedBuilder(
      animation: _pulse,
      builder: (_, child) => Opacity(
        opacity: widget.animate &&
                (widget.status == MotorStatus.critical ||
                    widget.status == MotorStatus.warning)
            ? _pulse.value
            : 1.0,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(4),
            border: Border.all(color: fg.withValues(alpha: 0.5)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  color: fg,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(color: fg.withValues(alpha: 0.5), blurRadius: 4),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              Text(
                label,
                style: AppTextStyles.labelMono.copyWith(
                  color: fg,
                  fontSize: 10,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
