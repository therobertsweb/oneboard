import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'feature_catalog.dart';

bool findingIsIgnored(Map<String, dynamic> finding) =>
    finding['status']?.toString() == 'ignored';

Color findingSeverityColor(String severity) => switch (severity.toLowerCase()) {
  'critical' || 'error' => const Color(0xFFB33142),
  'warning' => const Color(0xFFB25E09),
  _ => boardBlue,
};

String findingTitle(Map<String, dynamic> finding) {
  final check = finding['check']?.toString() ?? '';
  final page = finding['page']?.toString() ?? '';
  final humanized = check.replaceAll('_', ' ').trim();
  final titled = humanized.isEmpty
      ? 'Issue'
      : humanized[0].toUpperCase() + humanized.substring(1);
  return page.isEmpty ? titled : '$titled · $page';
}

String findingProposalText(Map<String, dynamic> finding) {
  final proposal = finding['proposal'];
  if (proposal is! Map) return '';
  for (final key in ['summary', 'message', 'action', 'description']) {
    final value = proposal[key];
    if (value is String && value.trim().isNotEmpty) return value.trim();
  }
  return '';
}

/// Site Health: scan summary, bulk actions, and one card per finding with
/// direct apply/ignore/reopen actions routed through the parent action runner.
class HealthPanel extends StatelessWidget {
  const HealthPanel({
    super.key,
    required this.health,
    required this.actions,
    required this.busy,
    required this.onRunAction,
  });

  final Map<String, dynamic> health;
  final List<FeatureAction> actions;
  final bool busy;
  final void Function(FeatureAction action, {Map<String, String>? pathOverrides})
  onRunAction;

  FeatureAction? _named(String label) {
    for (final action in actions) {
      if (action.label == label) return action;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final findings =
        (health['findings'] as List?)?.whereType<Map>().toList() ?? [];
    final ignored =
        (health['ignored'] as List?)?.whereType<Map>().toList() ?? [];
    final openCount = health['open_count'] ?? findings.length;
    final lastScan = (health['last_scan'] as Map?)?['created_at']?.toString() ?? '';
    final canEdit = health['can_edit'] != false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Open issues ($openCount)',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: boardInk,
                      ),
                    ),
                  ),
                  if (!canEdit)
                    const Text(
                      'View-only access',
                      style: TextStyle(color: boardMuted, fontSize: 12),
                    ),
                ],
              ),
              if (lastScan.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  'Last scan: $lastScan',
                  style: const TextStyle(color: boardMuted, fontSize: 12),
                ),
              ],
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final label in [
                    'Scan site',
                    'Apply automatic fixes',
                    'Explain issues with AI',
                    'Fix issues with AI',
                  ])
                    if (_named(label) != null)
                      OutlinedButton(
                        onPressed: !busy && canEdit
                            ? () => onRunAction(_named(label)!)
                            : null,
                        child: Text(label),
                      ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        if (findings.isEmpty && ignored.isEmpty)
          const BoardSurface(
            child: Text(
              'No issues found. Run a scan to check the connected site.',
              style: TextStyle(color: boardMuted, fontSize: 13),
            ),
          ),
        for (final finding in findings)
          _FindingCard(
            finding: finding.cast<String, dynamic>(),
            busy: busy,
            canEdit: canEdit,
            onRunAction: onRunAction,
            applyAction: _named('Apply fix'),
            ignoreAction: _named('Ignore finding'),
            reopenAction: _named('Reopen finding'),
          ),
        if (ignored.isNotEmpty) ...[
          const SizedBox(height: 8),
          Text(
            'Ignored (${ignored.length})',
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w700,
              color: boardInk,
            ),
          ),
          const SizedBox(height: 9),
          for (final finding in ignored)
            _FindingCard(
              finding: finding.cast<String, dynamic>(),
              busy: busy,
              canEdit: canEdit,
              onRunAction: onRunAction,
              applyAction: _named('Apply fix'),
              ignoreAction: _named('Ignore finding'),
              reopenAction: _named('Reopen finding'),
            ),
        ],
      ],
    );
  }
}

class _FindingCard extends StatelessWidget {
  const _FindingCard({
    required this.finding,
    required this.busy,
    required this.canEdit,
    required this.onRunAction,
    required this.applyAction,
    required this.ignoreAction,
    required this.reopenAction,
  });

  final Map<String, dynamic> finding;
  final bool busy;
  final bool canEdit;
  final void Function(FeatureAction action, {Map<String, String>? pathOverrides})
  onRunAction;
  final FeatureAction? applyAction;
  final FeatureAction? ignoreAction;
  final FeatureAction? reopenAction;

  @override
  Widget build(BuildContext context) {
    final ignored = findingIsIgnored(finding);
    final severity = finding['severity']?.toString() ?? 'warning';
    final detail = finding['detail']?.toString() ?? '';
    final proposal = findingProposalText(finding);
    final id = '${finding['id'] ?? ''}';
    return Padding(
      padding: const EdgeInsets.only(bottom: 9),
      child: BoardSurface(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 9,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: findingSeverityColor(
                      severity,
                    ).withValues(alpha: .12),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    severity.toUpperCase(),
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      color: findingSeverityColor(severity),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    findingTitle(finding),
                    style: const TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: boardInk,
                    ),
                  ),
                ),
              ],
            ),
            if (detail.isNotEmpty) ...[
              const SizedBox(height: 8),
              SelectableText(
                detail,
                style: const TextStyle(
                  color: boardInk,
                  fontSize: 13,
                  height: 1.5,
                ),
              ),
            ],
            if (proposal.isNotEmpty) ...[
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(11),
                decoration: BoxDecoration(
                  color: boardBlue.withValues(alpha: .07),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  proposal,
                  style: const TextStyle(
                    color: Color(0xFF245A9C),
                    fontSize: 12,
                    height: 1.5,
                  ),
                ),
              ),
            ],
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (!ignored && applyAction != null)
                  OutlinedButton(
                    onPressed: !busy && canEdit && id.isNotEmpty
                        ? () => onRunAction(
                            applyAction!,
                            pathOverrides: {'finding_id': id},
                          )
                        : null,
                    child: const Text('Apply fix'),
                  ),
                if (!ignored && ignoreAction != null)
                  TextButton(
                    onPressed: !busy && canEdit && id.isNotEmpty
                        ? () => onRunAction(
                            ignoreAction!,
                            pathOverrides: {'finding_id': id},
                          )
                        : null,
                    child: const Text('Ignore'),
                  ),
                if (ignored && reopenAction != null)
                  OutlinedButton(
                    onPressed: !busy && canEdit && id.isNotEmpty
                        ? () => onRunAction(
                            reopenAction!,
                            pathOverrides: {'finding_id': id},
                          )
                        : null,
                    child: const Text('Reopen'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
