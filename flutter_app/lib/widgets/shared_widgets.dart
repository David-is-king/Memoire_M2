// lib/widgets/shared_widgets.dart

import 'package:flutter/material.dart';
import '../models/models.dart';
import '../theme/app_theme.dart';

// ── StatusBadge ───────────────────────────────────────────
class StatusBadge extends StatelessWidget {
  final DeviceStatus status;
  const StatusBadge({super.key, required this.status});

  ({Color fg, Color bg, String label}) get _cfg => switch (status) {
    DeviceStatus.healthy  => (fg: AppColors.healthy,  bg: AppColors.healthyBg,  label: 'Healthy'),
    DeviceStatus.warning  => (fg: AppColors.warning,  bg: AppColors.warningBg,  label: 'Warning'),
    DeviceStatus.critical => (fg: AppColors.critical, bg: AppColors.criticalBg, label: 'Critical'),
    DeviceStatus.offline  => (fg: AppColors.textLight, bg: AppColors.border,    label: 'Offline'),
  };

  @override
  Widget build(BuildContext context) {
    final c = _cfg;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: c.bg, borderRadius: BorderRadius.circular(20)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(width: 6, height: 6, decoration: BoxDecoration(color: c.fg, shape: BoxShape.circle)),
        const SizedBox(width: 5),
        Text(c.label, style: TextStyle(fontFamily: 'Nunito', fontSize: 11, fontWeight: FontWeight.w700, color: c.fg)),
      ]),
    );
  }
}

// ── AlertSeverityBadge ────────────────────────────────────
class AlertBadge extends StatelessWidget {
  final AlertSeverity severity;
  const AlertBadge({super.key, required this.severity});

  ({Color fg, Color bg, String label}) get _cfg => switch (severity) {
    AlertSeverity.critical => (fg: AppColors.critical, bg: AppColors.criticalBg, label: 'Critical'),
    AlertSeverity.warning  => (fg: AppColors.warning,  bg: AppColors.warningBg,  label: 'Warning'),
    AlertSeverity.info     => (fg: AppColors.info,     bg: AppColors.infoBg,     label: 'Info'),
    AlertSeverity.ok       => (fg: AppColors.healthy,  bg: AppColors.healthyBg,  label: 'OK'),
  };

  @override
  Widget build(BuildContext context) {
    final c = _cfg;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(color: c.bg, borderRadius: BorderRadius.circular(20)),
      child: Text(c.label, style: TextStyle(fontFamily: 'Nunito', fontSize: 11, fontWeight: FontWeight.w700, color: c.fg)),
    );
  }
}

// ── StatCard (dashboard top grid) ────────────────────────
class StatCard extends StatelessWidget {
  final String label;
  final String value;
  final Color iconBg;
  final IconData icon;
  final Color? valueColor;

  const StatCard({
    super.key, required this.label, required this.value,
    required this.iconBg, required this.icon, this.valueColor,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        boxShadow: cardShadow(),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: 36, height: 36,
          decoration: BoxDecoration(color: iconBg, borderRadius: BorderRadius.circular(10)),
          child: Icon(icon, color: AppColors.surface, size: 18),
        ),
        const SizedBox(height: 10),
        Text(value, style: AppText.numM.copyWith(color: valueColor ?? AppColors.textDark, fontSize: 22)),
        const SizedBox(height: 2),
        Text(label, style: AppText.sm),
      ]),
    );
  }
}

// ── HealthRing (circular progress) ───────────────────────
class HealthRing extends StatelessWidget {
  final int score;
  final double size;
  final double strokeWidth;

  const HealthRing({super.key, required this.score, this.size = 44, this.strokeWidth = 4});

  Color get _color {
    if (score >= 75) return AppColors.healthy;
    if (score >= 50) return AppColors.warning;
    return AppColors.critical;
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size, height: size,
      child: Stack(alignment: Alignment.center, children: [
        CircularProgressIndicator(
          value: score / 100,
          strokeWidth: strokeWidth,
          backgroundColor: AppColors.border,
          valueColor: AlwaysStoppedAnimation(_color),
          strokeCap: StrokeCap.round,
        ),
        Text('$score%', style: TextStyle(fontFamily: 'Nunito', fontSize: size * 0.22, fontWeight: FontWeight.w700, color: AppColors.textDark)),
      ]),
    );
  }
}

// ── DeviceListTile ────────────────────────────────────────
class DeviceListTile extends StatelessWidget {
  final MotorDevice device;
  final VoidCallback? onTap;

  const DeviceListTile({super.key, required this.device, this.onTap});

  ({Color bg, IconData icon}) get _iconCfg => switch (device.status) {
    DeviceStatus.healthy  => (bg: AppColors.primaryLight, icon: Icons.memory_rounded),
    DeviceStatus.warning  => (bg: AppColors.warningBg,   icon: Icons.memory_rounded),
    DeviceStatus.critical => (bg: AppColors.criticalBg,  icon: Icons.memory_rounded),
    DeviceStatus.offline  => (bg: AppColors.border,      icon: Icons.memory_rounded),
  };

  Color get _statusColor => switch (device.status) {
    DeviceStatus.healthy  => AppColors.healthy,
    DeviceStatus.warning  => AppColors.warning,
    DeviceStatus.critical => AppColors.critical,
    DeviceStatus.offline  => AppColors.textLight,
  };

  String get _statusLabel => switch (device.status) {
    DeviceStatus.healthy  => 'Healthy',
    DeviceStatus.warning  => 'Warning',
    DeviceStatus.critical => 'Critical',
    DeviceStatus.offline  => 'Offline',
  };

  @override
  Widget build(BuildContext context) {
    final ic = _iconCfg;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(16),
          boxShadow: cardShadow(),
        ),
        child: Row(children: [
          Container(
            width: 44, height: 44,
            decoration: BoxDecoration(color: ic.bg, borderRadius: BorderRadius.circular(12)),
            child: Icon(ic.icon, color: _statusColor, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(device.name, style: AppText.h3),
              const SizedBox(height: 2),
              Row(children: [
                Container(width: 6, height: 6,
                  decoration: BoxDecoration(color: _statusColor, shape: BoxShape.circle)),
                const SizedBox(width: 5),
                Text(_statusLabel, style: TextStyle(fontFamily: 'Nunito', fontSize: 12, fontWeight: FontWeight.w600, color: _statusColor)),
              ]),
            ],
          )),
          const SizedBox(width: 8),
          HealthRing(score: device.healthScore),
        ]),
      ),
    );
  }
}

// ── SectionHeader ─────────────────────────────────────────
class SectionHeader extends StatelessWidget {
  final String title;
  final String? actionLabel;
  final VoidCallback? onAction;

  const SectionHeader({super.key, required this.title, this.actionLabel, this.onAction});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(title, style: AppText.h2),
        if (actionLabel != null)
          GestureDetector(
            onTap: onAction,
            child: Text(actionLabel!, style: const TextStyle(
              fontFamily: 'Nunito', fontSize: 13,
              fontWeight: FontWeight.w600, color: AppColors.primary,
            )),
          ),
      ],
    );
  }
}

// ── SensorMetricTile ──────────────────────────────────────
class SensorMetricTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final bool isAlert;

  const SensorMetricTile({
    super.key, required this.icon, required this.label,
    required this.value, this.isAlert = false,
  });

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Icon(icon, color: isAlert ? AppColors.critical : AppColors.primary, size: 22),
      const SizedBox(height: 4),
      Text(value, style: TextStyle(
        fontFamily: 'Nunito', fontSize: 14, fontWeight: FontWeight.w700,
        color: isAlert ? AppColors.critical : AppColors.textDark,
      )),
      Text(label, style: AppText.sm.copyWith(fontSize: 10)),
    ]);
  }
}

// ── PrimaryButton ─────────────────────────────────────────
class PrimaryButton extends StatelessWidget {
  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool loading;

  const PrimaryButton({super.key, required this.label, this.icon, this.onTap, this.loading = false});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          gradient: const LinearGradient(colors: [Color(0xFF3B82F6), Color(0xFF1D4ED8)]),
          borderRadius: BorderRadius.circular(16),
          boxShadow: blueShadow(),
        ),
        child: loading
            ? const Center(child: SizedBox(width: 20, height: 20, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2)))
            : Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                Text(label, style: const TextStyle(fontFamily: 'Nunito', fontSize: 15, fontWeight: FontWeight.w700, color: Colors.white)),
                if (icon != null) ...[const SizedBox(width: 8), Icon(icon, color: Colors.white, size: 18)],
              ]),
      ),
    );
  }
}