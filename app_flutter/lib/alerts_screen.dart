// screens/alerts_screen.dart
import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'app_theme.dart';

class AlertsScreen extends StatefulWidget {
  const AlertsScreen({super.key});

  @override
  State<AlertsScreen> createState() => _AlertsScreenState();
}

class _AlertsScreenState extends State<AlertsScreen> {
  final _api = ApiService();
  List<AlertModel> _alerts = [];
  bool _loading = true;
  AlertSeverity? _filter;

  @override
  void initState() {
    super.initState();
    _loadAlerts();
  }

  Future<void> _loadAlerts() async {
    try {
      final alerts = await _api.getAlerts();
      if (mounted) setState(() { _alerts = alerts; _loading = false; });
    } catch (_) {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _markAllRead() async {
    await _api.markAllAlertsRead();
    setState(() {
      _alerts = _alerts.map((a) => AlertModel(
        id: a.id, motorId: a.motorId, motorName: a.motorName,
        severity: a.severity, title: a.title, message: a.message,
        createdAt: a.createdAt, isRead: true,
      )).toList();
    });
  }

  Future<void> _markRead(AlertModel alert) async {
    await _api.markAlertRead(alert.id);
    setState(() {
      final idx = _alerts.indexWhere((a) => a.id == alert.id);
      if (idx != -1) {
        _alerts[idx] = AlertModel(
          id: alert.id, motorId: alert.motorId, motorName: alert.motorName,
          severity: alert.severity, title: alert.title, message: alert.message,
          createdAt: alert.createdAt, isRead: true,
        );
      }
    });
  }

  List<AlertModel> get _filtered {
    if (_filter == null) return _alerts;
    return _alerts.where((a) => a.severity == _filter).toList();
  }

  int _countFor(AlertSeverity s) =>
      _alerts.where((a) => a.severity == s).length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: AppTheme.background,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded,
              color: AppTheme.textSecondary, size: 18),
          onPressed: () => Navigator.pop(context),
        ),
        title: const Text('ALERTES', style: AppTextStyles.headingMedium),
        actions: [
          TextButton(
            onPressed: _markAllRead,
            child: Text(
              'TOUT LU',
              style: AppTextStyles.labelMono.copyWith(color: AppTheme.primary),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          // Filtres
          _buildFilterBar(),
          // Liste
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: AppTheme.primary))
                : _filtered.isEmpty
                    ? _buildEmpty()
                    : RefreshIndicator(
                        onRefresh: _loadAlerts,
                        color: AppTheme.primary,
                        backgroundColor: AppTheme.surfaceElevated,
                        child: ListView.separated(
                          padding: const EdgeInsets.all(16),
                          itemCount: _filtered.length,
                          separatorBuilder: (_, index) =>
                              const SizedBox(height: 8),
                          itemBuilder: (_, i) =>
                              _buildAlertTile(_filtered[i]),
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterBar() {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.border)),
      ),
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            _FilterChip(
              label: 'TOUS',
              count: _alerts.length,
              color: AppTheme.textSecondary,
              selected: _filter == null,
              onTap: () => setState(() => _filter = null),
            ),
            const SizedBox(width: 8),
            _FilterChip(
              label: 'CRITIQUE',
              count: _countFor(AlertSeverity.critical),
              color: AppTheme.danger,
              selected: _filter == AlertSeverity.critical,
              onTap: () => setState(() =>
                  _filter = _filter == AlertSeverity.critical
                      ? null
                      : AlertSeverity.critical),
            ),
            const SizedBox(width: 8),
            _FilterChip(
              label: 'ALERTE',
              count: _countFor(AlertSeverity.warning),
              color: AppTheme.warning,
              selected: _filter == AlertSeverity.warning,
              onTap: () => setState(() =>
                  _filter = _filter == AlertSeverity.warning
                      ? null
                      : AlertSeverity.warning),
            ),
            const SizedBox(width: 8),
            _FilterChip(
              label: 'INFO',
              count: _countFor(AlertSeverity.info),
              color: AppTheme.primary,
              selected: _filter == AlertSeverity.info,
              onTap: () => setState(() =>
                  _filter = _filter == AlertSeverity.info
                      ? null
                      : AlertSeverity.info),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAlertTile(AlertModel alert) {
    final (color, icon) = switch (alert.severity) {
      AlertSeverity.critical => (AppTheme.danger, Icons.crisis_alert_rounded),
      AlertSeverity.warning => (AppTheme.warning, Icons.warning_amber_rounded),
      AlertSeverity.info => (AppTheme.primary, Icons.info_outline_rounded),
    };

    return GestureDetector(
      onTap: () => _markRead(alert),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: alert.isRead
              ? AppTheme.surface
              : color.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: alert.isRead
                ? AppTheme.border
                : color.withValues(alpha: 0.3),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Icone
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: color, size: 16),
            ),
            const SizedBox(width: 12),
            // Contenu
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          alert.title,
                          style: TextStyle(
                            color: alert.isRead
                                ? AppTheme.textSecondary
                                : AppTheme.textPrimary,
                            fontSize: 13,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ),
                      if (!alert.isRead)
                        Container(
                          width: 6,
                          height: 6,
                          decoration: BoxDecoration(
                            color: color,
                            shape: BoxShape.circle,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    alert.motorName,
                    style: AppTextStyles.labelMono.copyWith(
                      color: color,
                      fontSize: 9,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    alert.message,
                    style: TextStyle(
                      color: AppTheme.textSecondary,
                      fontSize: 12,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _formatRelative(alert.createdAt),
                    style: AppTextStyles.labelMono.copyWith(fontSize: 9),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty() => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.notifications_off_outlined,
                color: AppTheme.textMuted, size: 48),
            const SizedBox(height: 12),
            Text(
              'AUCUNE ALERTE',
              style: AppTextStyles.labelMono.copyWith(
                color: AppTheme.textMuted,
              ),
            ),
          ],
        ),
      );

  String _formatRelative(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inMinutes < 60) return 'Il y a ${diff.inMinutes} min';
    if (diff.inHours < 24) return 'Il y a ${diff.inHours}h';
    return 'Il y a ${diff.inDays}j';
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final int count;
  final Color color;
  final bool selected;
  final VoidCallback onTap;

  const _FilterChip({
    required this.label,
    required this.count,
    required this.color,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: selected ? color.withValues(alpha: 0.15) : AppTheme.surface,
          borderRadius: BorderRadius.circular(6),
          border: Border.all(
            color: selected ? color.withValues(alpha: 0.5) : AppTheme.border,
          ),
        ),
        child: Row(
          children: [
            Text(
              label,
              style: AppTextStyles.labelMono.copyWith(
                color: selected ? color : AppTheme.textSecondary,
                fontSize: 9,
              ),
            ),
            const SizedBox(width: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
              decoration: BoxDecoration(
                color: color.withValues(alpha: selected ? 0.25 : 0.1),
                borderRadius: BorderRadius.circular(3),
              ),
              child: Text(
                '$count',
                style: AppTextStyles.labelMono.copyWith(
                  color: color,
                  fontSize: 8,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
