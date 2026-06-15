// ─────────────────────────────────────────────
// screens/dashboard_screen.dart
// ─────────────────────────────────────────────

import 'dart:async';
import 'package:flutter/material.dart';
import 'sensor_data.dart';
import 'api_service.dart';
import 'websocket_service.dart';
import 'notification_service.dart';
import 'app_theme.dart';
import 'sensor_card.dart';
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
    // Refresh toutes les 30s
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
          _recentAlerts = alerts.take(5).toList();
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
        if (_recentAlerts.length > 5) _recentAlerts.removeLast();
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

  // ── Stats globales ───────────────────────────

  int get _healthyCount =>
      _motors.where((m) => m.status == MotorStatus.healthy).length;
  int get _warningCount =>
      _motors.where((m) => m.status == MotorStatus.warning).length;
  int get _criticalCount =>
      _motors.where((m) => m.status == MotorStatus.critical).length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(),
            Expanded(
              child: _loading
                  ? _buildLoader()
                  : _error != null
                      ? _buildError()
                      : _buildContent(),
            ),
          ],
        ),
      ),
    );
  }

  // ── Header ───────────────────────────────────

  Widget _buildHeader() {
    return Container(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: AppTheme.border)),
      ),
      child: Row(
        children: [
          // Logo / Titre
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'smartpredict',
                style: AppTextStyles.labelMono.copyWith(
                  color: AppTheme.primary,
                  letterSpacing: 4,
                  fontSize: 10,
                ),
              ),
              const Text('MAINTENANCE', style: AppTextStyles.headingMedium),
            ],
          ),
          const Spacer(),
          // Statut WS
          StreamBuilder<WsConnectionState>(
            stream: _ws.connectionState,
            builder: (_, snap) {
              final connected =
                  snap.data == WsConnectionState.connected;
              return Row(
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(
                      color: connected
                          ? AppTheme.accent
                          : AppTheme.textMuted,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    connected ? 'LIVE' : 'OFFLINE',
                    style: AppTextStyles.labelMono.copyWith(fontSize: 9),
                  ),
                ],
              );
            },
          ),
          const SizedBox(width: 16),
          // Cloche alertes
          GestureDetector(
            onTap: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const AlertsScreen()),
            ),
            child: Stack(
              children: [
                const Icon(Icons.notifications_none_rounded,
                    color: AppTheme.textSecondary),
                if (_unreadCount > 0)
                  Positioned(
                    top: 0,
                    right: 0,
                    child: Container(
                      width: 14,
                      height: 14,
                      decoration: const BoxDecoration(
                        color: AppTheme.danger,
                        shape: BoxShape.circle,
                      ),
                      child: Center(
                        child: Text(
                          _unreadCount > 9 ? '9+' : '$_unreadCount',
                          style: const TextStyle(
                            fontSize: 8,
                            color: Colors.white,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Stats bar ────────────────────────────────

  Widget _buildStatsBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
      child: Row(
        children: [
          _StatChip(
            value: '${_motors.length}',
            label: 'MOTEURS',
            color: AppTheme.textSecondary,
          ),
          const SizedBox(width: 12),
          _StatChip(
            value: '$_healthyCount',
            label: 'OK',
            color: AppTheme.accent,
          ),
          const SizedBox(width: 12),
          _StatChip(
            value: '$_warningCount',
            label: 'ALERTE',
            color: AppTheme.warning,
          ),
          const SizedBox(width: 12),
          _StatChip(
            value: '$_criticalCount',
            label: 'CRITIQUE',
            color: AppTheme.danger,
          ),
        ],
      ),
    );
  }

  // ── Content ──────────────────────────────────

  Widget _buildContent() {
    return RefreshIndicator(
      onRefresh: _loadData,
      color: AppTheme.primary,
      backgroundColor: AppTheme.surfaceElevated,
      child: ListView(
        padding: const EdgeInsets.only(bottom: 32),
        children: [
          _buildStatsBar(),
          const SizedBox(height: 24),
          // Section critiques en premier
          if (_criticalCount > 0) ...[
            _SectionHeader(
              label: 'CRITIQUE',
              count: _criticalCount,
              color: AppTheme.danger,
            ),
            ..._motors
                .where((m) => m.status == MotorStatus.critical)
                .map(_buildMotorCard),
            const SizedBox(height: 8),
          ],
          if (_warningCount > 0) ...[
            _SectionHeader(
              label: 'ATTENTION',
              count: _warningCount,
              color: AppTheme.warning,
            ),
            ..._motors
                .where((m) => m.status == MotorStatus.warning)
                .map(_buildMotorCard),
            const SizedBox(height: 8),
          ],
          _SectionHeader(
            label: 'TOUS LES MOTEURS',
            count: _motors.length,
            color: AppTheme.textSecondary,
          ),
          ..._motors.map(_buildMotorCard),
        ],
      ),
    );
  }

  // ── Motor Card ───────────────────────────────

  Widget _buildMotorCard(MotorDevice motor) {
    final isCritical = motor.status == MotorStatus.critical;
    final isWarning = motor.status == MotorStatus.warning;

    return GestureDetector(
      onTap: () => Navigator.push(
        context,
        MaterialPageRoute(
          builder: (_) => MotorDetailScreen(motorId: motor.id),
        ),
      ),
      child: Container(
        margin: const EdgeInsets.fromLTRB(20, 0, 20, 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isCritical
              ? AppTheme.dangerDim
              : isWarning
                  ? AppTheme.warningDim
                  : AppTheme.surface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isCritical
                ? AppTheme.danger.withValues(alpha: 0.4)
                : isWarning
                    ? AppTheme.warning.withValues(alpha: 0.4)
                    : AppTheme.border,
          ),
        ),
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(motor.name, style: AppTextStyles.headingMedium),
                      const SizedBox(height: 2),
                      Text(
                        motor.location.toUpperCase(),
                        style: AppTextStyles.labelMono,
                      ),
                    ],
                  ),
                ),
                StatusBadge(status: motor.status),
              ],
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                // Health
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'SANTÉ',
                        style: AppTextStyles.labelMono.copyWith(fontSize: 9),
                      ),
                      const SizedBox(height: 4),
                      ClipRRect(
                        borderRadius: BorderRadius.circular(2),
                        child: LinearProgressIndicator(
                          value: motor.healthScore,
                          backgroundColor: AppTheme.border,
                          valueColor: AlwaysStoppedAnimation(
                            motor.healthScore >= 0.75
                                ? AppTheme.accent
                                : motor.healthScore >= 0.50
                                    ? AppTheme.warning
                                    : AppTheme.danger,
                          ),
                          minHeight: 4,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${(motor.healthScore * 100).toInt()}%',
                        style: AppTextStyles.labelMono.copyWith(
                          color: AppTheme.textPrimary,
                          fontSize: 10,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 20),
                // Failure prob
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      'RISQUE PANNE',
                      style: AppTextStyles.labelMono.copyWith(fontSize: 9),
                    ),
                    Text(
                      '${(motor.failureProbability * 100).toInt()}%',
                      style: AppTextStyles.valueSmall.copyWith(
                        color: motor.failureProbability > 0.7
                            ? AppTheme.danger
                            : motor.failureProbability > 0.4
                                ? AppTheme.warning
                                : AppTheme.accent,
                        fontSize: 22,
                      ),
                    ),
                  ],
                ),
                const SizedBox(width: 20),
                // RUL
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      'RUL',
                      style: AppTextStyles.labelMono.copyWith(fontSize: 9),
                    ),
                    Text(
                      '${motor.estimatedRulDays}j',
                      style: AppTextStyles.valueSmall.copyWith(fontSize: 22),
                    ),
                  ],
                ),
              ],
            ),
            if (motor.lastReading != null) ...[
              const SizedBox(height: 12),
              const Divider(color: AppTheme.border, height: 1),
              const SizedBox(height: 12),
              Row(
                children: [
                  _MiniStat(
                    icon: Icons.thermostat_rounded,
                    value:
                        '${motor.lastReading!.temperature.toStringAsFixed(1)}°C',
                    alert: motor.lastReading!.temperature > 85,
                  ),
                  _MiniStat(
                    icon: Icons.vibration_rounded,
                    value:
                        '${motor.lastReading!.vibrationRms.toStringAsFixed(2)} m/s²',
                    alert: motor.lastReading!.vibrationRms > 5,
                  ),
                  _MiniStat(
                    icon: Icons.electric_bolt_rounded,
                    value:
                        '${motor.lastReading!.current.toStringAsFixed(1)} A',
                    alert: false,
                  ),
                  _MiniStat(
                    icon: Icons.graphic_eq_rounded,
                    value:
                        '${motor.lastReading!.acousticDb.toStringAsFixed(0)} dB',
                    alert: motor.lastReading!.acousticDb > 85,
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildLoader() => const Center(
        child: CircularProgressIndicator(color: AppTheme.primary),
      );

  Widget _buildError() => Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppTheme.danger, size: 48),
            const SizedBox(height: 16),
            Text('Connexion impossible', style: AppTextStyles.headingMedium),
            const SizedBox(height: 8),
            Text(_error ?? '', style: AppTextStyles.labelMono),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: _loadData,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.primaryDim,
                foregroundColor: AppTheme.primary,
              ),
              child: const Text('RÉESSAYER'),
            ),
          ],
        ),
      );
}

// ── Sous-widgets ─────────────────────────────

class _StatChip extends StatelessWidget {
  final String value;
  final String label;
  final Color color;

  const _StatChip({
    required this.value,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          Text(
            value,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w800,
              color: color,
              fontFamily: 'Courier',
            ),
          ),
          Text(
            label,
            style: AppTextStyles.labelMono.copyWith(fontSize: 8),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String label;
  final int count;
  final Color color;

  const _SectionHeader({
    required this.label,
    required this.count,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
      child: Row(
        children: [
          Text(
            label,
            style: AppTextStyles.labelMono.copyWith(color: color),
          ),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(3),
            ),
            child: Text(
              '$count',
              style: AppTextStyles.labelMono.copyWith(
                color: color,
                fontSize: 9,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(child: Divider(color: color.withValues(alpha: 0.2))),
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  final IconData icon;
  final String value;
  final bool alert;

  const _MiniStat({
    required this.icon,
    required this.value,
    required this.alert,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Row(
        children: [
          Icon(icon,
              size: 12,
              color: alert ? AppTheme.danger : AppTheme.textMuted),
          const SizedBox(width: 3),
          Flexible(
            child: Text(
              value,
              style: AppTextStyles.labelMono.copyWith(
                fontSize: 9,
                color: alert ? AppTheme.danger : AppTheme.textSecondary,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}
