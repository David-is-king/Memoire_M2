// ─────────────────────────────────────────────
// widgets/status_badge.dart
// Badge de statut style "pilule" (Critique / Alerte / OK / Hors ligne)
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'app_theme.dart';
import 'sensor_data.dart';

class StatusBadge extends StatelessWidget {
  final MotorStatus status;
  final bool animate; // conservé pour compat API, non utilisé visuellement

  const StatusBadge({
    super.key,
    required this.status,
    this.animate = true,
  });

  (Color, Color, String) get _config => switch (status) {
        MotorStatus.healthy => (AppTheme.success, AppTheme.successBg, 'OK'),
        MotorStatus.warning => (AppTheme.warning, AppTheme.warningBg, 'Alerte'),
        MotorStatus.critical => (AppTheme.danger, AppTheme.dangerBg, 'Critique'),
        MotorStatus.offline => (AppTheme.textMuted, AppTheme.surfaceElevated, 'Hors ligne'),
      };

  @override
  Widget build(BuildContext context) {
    final (fg, bg, label) = _config;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: fg,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

/// Icône représentant le type de machine (selon son nom), avec un
/// fond coloré arrondi, comme dans la maquette.
class MachineIcon extends StatelessWidget {
  final String machineName;
  final double size;

  const MachineIcon({super.key, required this.machineName, this.size = 44});

  IconData get _icon {
    final n = machineName.toLowerCase();
    if (n.contains('presse')) return Icons.compress_rounded;
    if (n.contains('convoyeur')) return Icons.settings_input_component_rounded;
    if (n.contains('compresseur')) return Icons.air_rounded;
    if (n.contains('pompe')) return Icons.water_drop_rounded;
    return Icons.precision_manufacturing_rounded;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: AppTheme.primary.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(_icon, color: AppTheme.primary, size: size * 0.5),
    );
  }
}
