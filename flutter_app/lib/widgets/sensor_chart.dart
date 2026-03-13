// lib/widgets/sensor_chart.dart

import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';

class SensorChart extends StatelessWidget {
  final List<ChartPoint> points;
  final Color color;
  final double? minY;
  final double? maxY;
  final double height;

  const SensorChart({
    super.key, required this.points, this.color = AppColors.primary,
    this.minY, this.maxY, this.height = 160,
  });

  List<FlSpot> get _spots {
    if (points.isEmpty) return [];
    final t0 = points.first.time.millisecondsSinceEpoch.toDouble();
    return points.map((p) => FlSpot(
      (p.time.millisecondsSinceEpoch - t0) / 60000, p.value,
    )).toList();
  }

  @override
  Widget build(BuildContext context) {
    final spots = _spots;
    if (spots.length < 2) {
      return SizedBox(height: height, child: Center(
        child: Text('Waiting for data…', style: AppText.sm),
      ));
    }

    return SizedBox(
      height: height,
      child: LineChart(LineChartData(
        minY: minY, maxY: maxY,
        gridData: FlGridData(
          show: true, drawVerticalLine: false,
          horizontalInterval: (maxY ?? 100) / 4,
          getDrawingHorizontalLine: (_) => FlLine(color: AppColors.border, strokeWidth: 1),
        ),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(sideTitles: SideTitles(
            showTitles: true, reservedSize: 28,
            getTitlesWidget: (v, _) => Text(v.toInt().toString(),
                style: AppText.sm.copyWith(fontSize: 10)),
          )),
          bottomTitles: AxisTitles(sideTitles: SideTitles(
            showTitles: true, reservedSize: 22, interval: spots.last.x / 4,
            getTitlesWidget: (v, _) {
              if (points.isEmpty) return const SizedBox();
              final dt = DateTime.fromMillisecondsSinceEpoch(
                (points.first.time.millisecondsSinceEpoch + v * 60000).toInt(),
              );
              return Text('${dt.hour.toString().padLeft(2,'0')}:${dt.minute.toString().padLeft(2,'0')}',
                  style: AppText.sm.copyWith(fontSize: 10));
            },
          )),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        lineBarsData: [LineChartBarData(
          spots: spots,
          isCurved: true, curveSmoothness: 0.35,
          color: color, barWidth: 2.5,
          isStrokeCapRound: true,
          dotData: FlDotData(
            show: true,
            checkToShowDot: (s, _) => s == spots.last,
            getDotPainter: (_, __, ___, ____) => FlDotCirclePainter(
              radius: 5, color: color,
              strokeColor: Colors.white, strokeWidth: 2,
            ),
          ),
          belowBarData: BarAreaData(
            show: true,
            gradient: LinearGradient(
              begin: Alignment.topCenter, end: Alignment.bottomCenter,
              colors: [color.withOpacity(0.18), color.withOpacity(0)],
            ),
          ),
        )],
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipItems: (spots) => spots.map((s) => LineTooltipItem(
              s.y.toStringAsFixed(1),
              const TextStyle(fontFamily: 'Nunito', fontWeight: FontWeight.w700, color: Colors.white, fontSize: 12),
            )).toList(),
          ),
        ),
      )),
    );
  }
}

// ── ChartTabSelector ─────────────────────────────────────
class ChartTabSelector extends StatelessWidget {
  final List<String> tabs;
  final int selectedIndex;
  final ValueChanged<int> onChanged;

  const ChartTabSelector({
    super.key, required this.tabs,
    required this.selectedIndex, required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: AppColors.border, borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: List.generate(tabs.length, (i) {
          final sel = i == selectedIndex;
          return Expanded(child: GestureDetector(
            onTap: () => onChanged(i),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 180),
              padding: const EdgeInsets.symmetric(vertical: 8),
              decoration: BoxDecoration(
                color: sel ? AppColors.primary : Colors.transparent,
                borderRadius: BorderRadius.circular(9),
                boxShadow: sel ? blueShadow() : [],
              ),
              child: Text(tabs[i],
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontFamily: 'Nunito', fontSize: 12, fontWeight: FontWeight.w700,
                  color: sel ? Colors.white : AppColors.textMid,
                ),
              ),
            ),
          ));
        }),
      ),
    );
  }
}