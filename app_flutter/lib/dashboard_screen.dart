// ─────────────────────────────────────────────
// screens/dashboard_screen.dart
// Ecran 2 : Accueil / Tableau de bord
// ─────────────────────────────────────────────

import 'dart:async';
import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'websocket_service.dart';
import 'notification_service.dart';
import 'app_theme.dart';
import 'status_badge.dart';
import 'motor_detail_screen.dart';
import 'alerts_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _api = ApiService();
  final _ws = WebSocketService();
  final _notif = NotificationService();

  List<MotorDevice> _motors = [];
  List<AlertModel> _recentAlerts = [];
  int _unreadCount = 0;
  bool _loading = true;
  String? _error;

  late StreamSubscription _alertSub;
  late StreamSubscription _statusSub;
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _notif.initialize();
    _loadData();
    _connectWebSocket();
    _refreshTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _loadData(),
    );
  }

  Future<void> _loadData() async {
    try {
      final motors = await _api.getMotors();
      final alerts = await _api.getAlerts(unreadOnly: false);
      if (mounted) {
        setState(() {
          _motors = motors;
          _recentAlerts = alerts.take(4).toList();
          _unreadCount = alerts.where((a) => !a.isRead).length;
          _loading = false;
          _error = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _loading = false;
        });
      }
    }
  }

  void _connectWebSocket() {
    _ws.connect();

    _alertSub = _ws.alerts.listen((alert) {
      _notif.showAlertNotification(alert);
      setState(() {
        _recentAlerts.insert(0, alert);
        if (_recentAlerts.length > 4) _recentAlerts.removeLast();
        if (!alert.isRead) _unreadCount++;
      });
    });

    _statusSub = _ws.motorStatuses.listen((statuses) {
      setState(() {
        _motors = _motors.map((m) {
          final newStatus = statuses[m.id];
          if (newStatus == null) return m;
          return MotorDevice(
            id: m.id,
            name: m.name,
            location: m.location,
            status: newStatus,
            healthScore: m.healthScore,
            failureProbability: m.failureProbability,
            estimatedRulDays: m.estimatedRulDays,
            lastReading: m.lastReading,
            lastSeen: DateTime.now(),
          );
        }).toList();
      });
    });
  }

  @override
  void dispose() {
    _alertSub.cancel();
    _statusSub.cancel();
    _ws.dispose();
    _refreshTimer?.cancel();
    super.dispose();
  }

  int get _criticalCount =>
      _motors.where((m) => m.status == MotorStatus.critical).length;
  int get _warningCount =>
      _motors.where((m) => m.status == MotorStatus.warning).length;
  int get _healthyCount =>
      _motors.where((m) => m.status == MotorStatus.healthy).length;
  int get _maintenanceCount =>
      _motors.where((m) => m.status == MotorStatus.offline).length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: _loading
                  ? const Center(
                      child: CircularProgressIndicator(color: AppTheme.primary))
                  : _error != null
                      ? _buildError()
                      : _buildContent(),
            ),
          ],
        ),
      ),
    );
  }

  // ── Header bleu marine ───────────────────────

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
      decoration: const BoxDecoration(
        color: AppTheme.headerBg,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(24),
          bottomRight: Radius.circular(24),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.menu_rounded, color: Colors.white),
              const SizedBox(width: 12),
              const CircleAvatar(
                radius: 18,
                backgroundColor: Colors.white24,
                child: Icon(Icons.person, color: Colors.white, size: 20),
              ),
              const SizedBox(width: 10),
              const Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Bonjour, Julien',
                        style: TextStyle(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w600)),
                    Text('Technicien',
                        style: TextStyle(color: Colors.white70, fontSize: 11)),
                  ],
                ),
              ),
              GestureDetector(
                onTap: () => Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const AlertsScreen()),
                ),
                child: Stack(
                  children: [
                    const Icon(Icons.notifications_none_rounded,
                        color: Colors.white),
                    if (_unreadCount > 0)
                      Positioned(
                        right: 0,
                        top: 0,
                        child: Container(
                          padding: const EdgeInsets.all(3),
                          decoration: const BoxDecoration(
                            color: AppTheme.danger,
                            shape: BoxShape.circle,
                          ),
                          constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                          child: Text(
                            _unreadCount > 9 ? '9+' : '$_unreadCount',
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                              fontSize: 8,
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 22),
          const Text('Aperçu',
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          Row(
            children: [
              _OverviewCard(value: '$_criticalCount', label: 'Alertes\ncritiques', color: AppTheme.danger),
              const SizedBox(width: 10),
              _OverviewCard(value: '$_warningCount', label: 'Alertes\nmajeures', color: AppTheme.warning),
              const SizedBox(width: 10),
              _OverviewCard(value: '$_healthyCount', label: 'Machines\nOK', color: AppTheme.success),
              const SizedBox(width: 10),
              _OverviewCard(value: '$_maintenanceCount', label: 'En\nmaintenance', color: Colors.white),
            ],
          ),
        ],
      ),
    );
  }

  // ── Contenu ──────────────────────────────────

  Widget _buildContent() {
    return RefreshIndicator(
      onRefresh: _loadData,
      color: AppTheme.primary,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('Machines', style: AppTextStyles.headingMedium),
              TextButton(
                onPressed: () {},
                child: const Text('Voir tout',
                    style: TextStyle(color: AppTheme.primary, fontSize: 13)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ..._motors.take(4).map(_buildMachineRow),
        ],
      ),
    );
  }

  Widget _buildMachineRow(MotorDevice motor) {
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
                ],
              ),
            ),
            StatusBadge(status: motor.status),
          ],
        ),
      ),
    );
  }

  Widget _buildError() => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppTheme.danger, size: 48),
            const SizedBox(height: 16),
            const Text('Connexion impossible', style: AppTextStyles.headingMedium),
            const SizedBox(height: 8),
            Text(_error ?? '', style: AppTextStyles.labelMono),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _loadData,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primary,
                foregroundColor: Colors.white,
              ),
              child: const Text('Réessayer'),
            ),
          ],
        ),
      );
}

class _OverviewCard extends StatelessWidget {
  final String value;
  final String label;
  final Color color;

  const _OverviewCard({
    required this.value,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Text(
              value,
              style: TextStyle(
                fontSize: 22,
                fontWeight: FontWeight.w800,
                color: color,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 9,
                color: Colors.white70,
                height: 1.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
