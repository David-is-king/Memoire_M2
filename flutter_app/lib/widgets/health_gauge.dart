// lib/widgets/health_gauge.dart

import 'dart:math';
import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class HealthGauge extends StatefulWidget {
  final int score; // 0–100
  final double size;

  const HealthGauge({super.key, required this.score, this.size = 200});

  @override
  State<HealthGauge> createState() => _HealthGaugeState();
}

class _HealthGaugeState extends State<HealthGauge> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200));
    _anim = Tween<double>(begin: 0, end: widget.score / 100)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic));
    _ctrl.forward();
  }

  @override
  void didUpdateWidget(HealthGauge old) {
    super.didUpdateWidget(old);
    if (old.score != widget.score) {
      _anim = Tween<double>(begin: old.score / 100, end: widget.score / 100)
          .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOutCubic));
      _ctrl.forward(from: 0);
    }
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  String get _label {
    if (widget.score >= 75) return 'Healthy';
    if (widget.score >= 50) return 'Warning';
    return 'Critical';
  }

  Color get _labelColor {
    if (widget.score >= 75) return AppColors.healthy;
    if (widget.score >= 50) return AppColors.warning;
    return AppColors.critical;
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, __) => SizedBox(
        width: widget.size,
        height: widget.size * 0.65,
        child: Stack(alignment: Alignment.bottomCenter, children: [
          CustomPaint(
            size: Size(widget.size, widget.size * 0.65),
            painter: _GaugePainter(value: _anim.value),
          ),
          Positioned(
            bottom: widget.size * 0.08,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Text(
                '${widget.score}',
                style: TextStyle(fontFamily: 'Nunito', fontSize: widget.size * 0.22,
                    fontWeight: FontWeight.w800, color: AppColors.textDark, height: 1),
              ),
              Text(
                '/100',
                style: TextStyle(fontFamily: 'Nunito', fontSize: widget.size * 0.08,
                    color: AppColors.textLight, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                decoration: BoxDecoration(
                  color: _labelColor.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(width: 7, height: 7,
                      decoration: BoxDecoration(color: _labelColor, shape: BoxShape.circle)),
                  const SizedBox(width: 5),
                  Text(_label, style: TextStyle(
                      fontFamily: 'Nunito', fontSize: widget.size * 0.075,
                      fontWeight: FontWeight.w700, color: _labelColor)),
                ]),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _GaugePainter extends CustomPainter {
  final double value; // 0.0–1.0

  _GaugePainter({required this.value});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height * 0.88;
    final r  = size.width * 0.44;
    const stroke = 14.0;

    final rect = Rect.fromCircle(center: Offset(cx, cy), radius: r);
    const startAngle = pi;           // 180°
    const sweepFull  = pi;           // 180° arc

    // Track
    canvas.drawArc(rect, startAngle, sweepFull, false,
      Paint()..color = const Color(0xFFE2E8F0)..strokeWidth = stroke
             ..style = PaintingStyle.stroke..strokeCap = StrokeCap.round);

    // Gradient foreground
    final gradient = SweepGradient(
      startAngle: startAngle,
      endAngle: startAngle + sweepFull,
      colors: const [Color(0xFFDC2626), Color(0xFFD97706), Color(0xFFFACC15), Color(0xFF4ADE80), Color(0xFF16A34A)],
      stops: const [0.0, 0.25, 0.5, 0.75, 1.0],
    );
    final paint = Paint()
      ..shader = gradient.createShader(rect)
      ..strokeWidth = stroke
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    canvas.drawArc(rect, startAngle, sweepFull * value, false, paint);

    // Needle dot
    final angle  = startAngle + sweepFull * value;
    final dotX   = cx + r * cos(angle);
    final dotY   = cy + r * sin(angle);
    canvas.drawCircle(Offset(dotX, dotY), 7,
      Paint()..color = Colors.white..style = PaintingStyle.fill);
    canvas.drawCircle(Offset(dotX, dotY), 7,
      Paint()..color = _colorFor(value)..style = PaintingStyle.stroke..strokeWidth = 2.5);
  }

  Color _colorFor(double v) {
    if (v >= 0.75) return const Color(0xFF16A34A);
    if (v >= 0.50) return const Color(0xFFD97706);
    return const Color(0xFFDC2626);
  }

  @override
  bool shouldRepaint(_GaugePainter old) => old.value != value;
}