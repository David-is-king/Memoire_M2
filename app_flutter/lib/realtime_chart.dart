// ─────────────────────────────────────────────
// widgets/realtime_chart.dart
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'sensor_data.dart';
import 'app_theme.dart';

class RealtimeChart extends StatelessWidget {
  final List<ChartDataPoint> dataPoints;
  final String label;
  final String unit;
  final Color color;
  final double? minY;
  final double? maxY;
  final double height;

  const RealtimeChart({
    super.key,
    required this.dataPoints,
    required this.label,
    required this.unit,
    this.color = AppTheme.primary,
    this.minY,
    this.maxY,
    this.height = 120,
  });

  List<FlSpot> get _spots {
    if (dataPoints.isEmpty) return [];
    final first = dataPoints.first.time.millisecondsSinceEpoch.toDouble();
    return dataPoints.map((p) {
      final x = (p.time.millisecondsSinceEpoch.toDouble() - first) / 1000;
      return FlSpot(x, p.value);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final spots = _spots;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(label.toUpperCase(), style: AppTextStyles.labelMono),
            const Spacer(),
            if (dataPoints.isNotEmpty)
              Text(
                '${dataPoints.last.value.toStringAsFixed(1)} $unit',
                style: AppTextStyles.labelMono.copyWith(
                  color: color,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        SizedBox(
          height: height,
          child: spots.length < 2
              ? Center(
                  child: Text('En attente de données...', style: AppTextStyles.labelMono),
                )
              : LineChart(
                  LineChartData(
                    gridData: FlGridData(
                      show: true,
                      drawVerticalLine: false,
                      horizontalInterval: (maxY ?? 100) / 4,
                      getDrawingHorizontalLine: (_) => FlLine(
                        color: AppTheme.border,
                        strokeWidth: 0.5,
                      ),
                    ),
                    titlesData: FlTitlesData(
                      leftTitles: AxisTitles(
                        sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: 32,
                          getTitlesWidget: (v, _) => Text(
                            v.toInt().toString(),
                            style: AppTextStyles.labelMono.copyWith(fontSize: 8),
                          ),
                        ),
                      ),
                      rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                      bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                    ),
                    borderData: FlBorderData(show: false),
                    minY: minY,
                    maxY: maxY,
                    lineBarsData: [
                      LineChartBarData(
                        spots: spots,
                        isCurved: true,
                        curveSmoothness: 0.3,
                        color: color,
                        barWidth: 2,
                        isStrokeCapRound: true,
                        dotData: const FlDotData(show: false),
                        belowBarData: BarAreaData(
                          show: true,
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            colors: [
                              color.withValues(alpha: 0.18),
                              color.withValues(alpha: 0.0),
                            ],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
        ),
      ],
    );
  }
}
