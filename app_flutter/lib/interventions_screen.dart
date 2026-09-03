// ─────────────────────────────────────────────
// screens/interventions_screen.dart
// Ecran 6 : Interventions (à faire / en cours / terminées)
// ─────────────────────────────────────────────

import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'app_theme.dart';
import 'status_badge.dart';
import 'intervention_detail_screen.dart';

class InterventionsScreen extends StatefulWidget {
  const InterventionsScreen({super.key});

  @override
  State<InterventionsScreen> createState() => _InterventionsScreenState();
}

class _InterventionsScreenState extends State<InterventionsScreen>
    with SingleTickerProviderStateMixin {
  final _api = ApiService();
  late TabController _tabController;
  List<InterventionModel> _interventions = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await _api.getInterventions();
      if (mounted) setState(() { _interventions = data; _loading = false; _error = null; });
    } catch (e) {
      if (mounted) setState(() { _loading = false; _error = e.toString(); });
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  List<InterventionModel> _byStatus(InterventionStatus s) =>
      _interventions.where((i) => i.status == s).toList();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        title: const Text('Interventions'),
        centerTitle: false,
        bottom: TabBar(
          controller: _tabController,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white60,
          indicatorColor: Colors.white,
          labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
          tabs: const [
            Tab(text: 'À faire'),
            Tab(text: 'En cours'),
            Tab(text: 'Terminées'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AppTheme.primary))
          : _error != null
              ? _buildError()
              : TabBarView(
                  controller: _tabController,
                  children: [
                    _buildList(_byStatus(InterventionStatus.todo)),
                    _buildList(_byStatus(InterventionStatus.inProgress)),
                    _buildList(_byStatus(InterventionStatus.done)),
                  ],
                ),
    );
  }

  Widget _buildList(List<InterventionModel> items) {
    if (items.isEmpty) {
      return Center(
        child: Text('Aucune intervention', style: AppTextStyles.labelMono.copyWith(color: AppTheme.textMuted)),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      color: AppTheme.primary,
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: items.length,
        separatorBuilder: (_, i) => const SizedBox(height: 10),
        itemBuilder: (_, i) => _buildTile(items[i]),
      ),
    );
  }

  Widget _buildTile(InterventionModel item) {
    final (color, label) = switch (item.priority) {
      InterventionPriority.critical => (AppTheme.danger, 'Critique'),
      InterventionPriority.major => (AppTheme.warning, 'Majeur'),
      InterventionPriority.normal => (AppTheme.primary, 'Planifié'),
      InterventionPriority.low => (AppTheme.success, 'Faible'),
    };

    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => InterventionDetailScreen(intervention: item)),
      ),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppTheme.surface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppTheme.border),
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.03), blurRadius: 6, offset: const Offset(0, 2)),
          ],
        ),
        child: Row(
          children: [
            MachineIcon(machineName: item.motorName, size: 40),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text(item.motorName, style: AppTextStyles.headingSmall)),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(6)),
                        child: Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w700)),
                      ),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(item.motorLocation, style: AppTextStyles.labelMono),
                  const SizedBox(height: 6),
                  Text(item.type, style: AppTextStyles.bodyText.copyWith(fontSize: 12)),
                  const SizedBox(height: 6),
                  Text(_formatDeadline(item.scheduledAt),
                      style: AppTextStyles.labelMono.copyWith(fontSize: 10, color: AppTheme.textSecondary)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatDeadline(DateTime dt) {
    final now = DateTime.now();
    final isToday = dt.year == now.year && dt.month == now.month && dt.day == now.day;
    if (isToday) return 'Aujourd\'hui';
    final diff = dt.difference(now).inDays;
    if (diff == 1) return 'Demain';
    return '${dt.day.toString().padLeft(2, '0')}/${dt.month.toString().padLeft(2, '0')}/${dt.year}';
  }

  Widget _buildError() => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppTheme.danger, size: 48),
            const SizedBox(height: 16),
            const Text('Impossible de charger les interventions', style: AppTextStyles.headingSmall),
            const SizedBox(height: 8),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(_error ?? '', textAlign: TextAlign.center, style: AppTextStyles.labelMono),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _load,
              style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primary, foregroundColor: Colors.white),
              child: const Text('Réessayer'),
            ),
          ],
        ),
      );
}
