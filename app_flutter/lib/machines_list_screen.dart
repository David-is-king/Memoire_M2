// ─────────────────────────────────────────────
// screens/machines_list_screen.dart
// Liste complète des machines (onglet bottom nav "Machines")
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'app_theme.dart';
import 'status_badge.dart';
import 'motor_detail_screen.dart';

class MachinesListScreen extends StatefulWidget {
  const MachinesListScreen({super.key});

  @override
  State<MachinesListScreen> createState() => _MachinesListScreenState();
}

class _MachinesListScreenState extends State<MachinesListScreen> {
  final _api = ApiService();
  List<MotorDevice> _motors = [];
  bool _loading = true;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final motors = await _api.getMotors();
      if (mounted) setState(() { _motors = motors; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  List<MotorDevice> get _filtered {
    if (_query.isEmpty) return _motors;
    final q = _query.toLowerCase();
    return _motors.where((m) =>
        m.name.toLowerCase().contains(q) ||
        m.location.toLowerCase().contains(q)).toList();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text('Machines'),
        centerTitle: false,
      ),
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                onChanged: (v) => setState(() => _query = v),
                decoration: InputDecoration(
                  hintText: 'Rechercher une machine...',
                  prefixIcon: const Icon(Icons.search, color: AppTheme.textMuted),
                  filled: true,
                  fillColor: AppTheme.surface,
                  contentPadding: const EdgeInsets.symmetric(vertical: 0),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppTheme.border),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppTheme.border),
                  ),
                ),
              ),
            ),
            Expanded(
              child: _loading
                  ? const Center(child: CircularProgressIndicator(color: AppTheme.primary))
                  : _filtered.isEmpty
                      ? const Center(
                          child: Text('Aucune machine trouvée',
                              style: AppTextStyles.labelMono))
                      : RefreshIndicator(
                          onRefresh: _load,
                          color: AppTheme.primary,
                          child: ListView.builder(
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                            itemCount: _filtered.length,
                            itemBuilder: (_, i) => _buildTile(_filtered[i]),
                          ),
                        ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTile(MotorDevice motor) {
    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => MotorDetailScreen(motorId: motor.id)),
      ),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppTheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppTheme.border),
        ),
        child: Row(
          children: [
            MachineIcon(machineName: motor.name),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(motor.name, style: AppTextStyles.headingSmall),
                  const SizedBox(height: 2),
                  Text(motor.location, style: AppTextStyles.labelMono),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(Icons.favorite_rounded,
                          size: 12,
                          color: motor.healthScore >= 0.75
                              ? AppTheme.success
                              : motor.healthScore >= 0.5
                                  ? AppTheme.warning
                                  : AppTheme.danger),
                      const SizedBox(width: 4),
                      Text('${(motor.healthScore * 100).toInt()}% santé',
                          style: AppTextStyles.labelMono.copyWith(fontSize: 10)),
                    ],
                  ),
                ],
              ),
            ),
            StatusBadge(status: motor.status),
          ],
        ),
      ),
    );
  }
}
