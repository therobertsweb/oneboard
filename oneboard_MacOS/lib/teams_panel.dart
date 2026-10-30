import 'package:flutter/material.dart';

import 'apple_design.dart';
import 'board_api.dart';
import 'feature_catalog.dart';

String memberLabel(Map<String, dynamic> member) {
  final name = member['name']?.toString() ?? '';
  final email = member['email']?.toString() ?? '';
  if (name.isNotEmpty && email.isNotEmpty) return '$name ($email)';
  if (name.isNotEmpty) return name;
  if (email.isNotEmpty) return email;
  return 'Member ${member['id'] ?? ''}';
}

Color roleColor(String role) => switch (role) {
  'owner' || 'admin' => const Color(0xFFB33142),
  'editor' => boardBlue,
  _ => boardMuted,
};

/// Teams overview: my teams, pending invitations for me, and team creation.
class TeamsPanel extends StatelessWidget {
  const TeamsPanel({
    super.key,
    required this.data,
    required this.actions,
    required this.busy,
    required this.onRunAction,
    required this.onOpenTeam,
  });

  final Map<String, dynamic> data;
  final List<FeatureAction> actions;
  final bool busy;
  final Future<void> Function(
    FeatureAction action, {
    Map<String, String>? pathOverrides,
  })
  onRunAction;
  final void Function(int teamId) onOpenTeam;

  FeatureAction? _named(String label) {
    for (final action in actions) {
      if (action.label == label) return action;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final teams = (data['teams'] as List?)?.whereType<Map>().toList() ?? [];
    final pending =
        (data['pending_invites'] as List?)?.whereType<Map>().toList() ?? [];
    final createAction = _named('Create team');
    final acceptAction = _named('Accept invitation by ID');
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
                      'My teams (${teams.length})',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: boardInk,
                      ),
                    ),
                  ),
                  if (createAction != null)
                    FilledButton(
                      onPressed: busy ? null : () => onRunAction(createAction),
                      child: const Text('Create team'),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              if (teams.isEmpty)
                const Text(
                  'You are not in any team yet. Create one to collaborate.',
                  style: TextStyle(color: boardMuted, fontSize: 13),
                ),
              for (final team in teams)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: InkWell(
                    onTap: () {
                      final id = int.tryParse('${team['id']}');
                      if (id != null) onOpenTeam(id);
                    },
                    borderRadius: BorderRadius.circular(10),
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF9F9FB),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  team['name']?.toString() ?? 'Team',
                                  style: const TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                    color: boardInk,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  [
                                    team['member_count'] != null
                                        ? '${team['member_count']} members'
                                        : '',
                                    team['project_count'] != null
                                        ? '${team['project_count']} projects'
                                        : '',
                                  ].where((part) => part.isNotEmpty).join(' · '),
                                  style: const TextStyle(
                                    color: boardMuted,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          if (team['member_role'] != null ||
                              team['my_role'] != null)
                            _roleChip(
                              (team['member_role'] ?? team['my_role'])
                                  .toString(),
                            ),
                          const SizedBox(width: 6),
                          const Icon(
                            Icons.chevron_right_rounded,
                            color: boardMuted,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
        if (pending.isNotEmpty) ...[
          const SizedBox(height: 16),
          BoardSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Pending invitations (${pending.length})',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: boardInk,
                  ),
                ),
                const SizedBox(height: 12),
                for (final invite in pending)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                invite['team_name']?.toString() ?? 'Team',
                                style: const TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                  color: boardInk,
                                ),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                [
                                  'Role: ${invite['role'] ?? ''}',
                                  if ((invite['invited_by_name']?.toString() ??
                                          '')
                                      .isNotEmpty)
                                    'from ${invite['invited_by_name']}',
                                ].join(' '),
                                style: const TextStyle(
                                  color: boardMuted,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ),
                        if (acceptAction != null)
                          OutlinedButton(
                            onPressed: busy
                                ? null
                                : () => onRunAction(
                                    acceptAction,
                                    pathOverrides: {
                                      'invite_id': '${invite['id']}',
                                    },
                                  ),
                            child: const Text('Accept'),
                          ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

Widget _roleChip(String role) => Container(
  padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
  decoration: BoxDecoration(
    color: roleColor(role).withValues(alpha: .12),
    borderRadius: BorderRadius.circular(20),
  ),
  child: Text(
    role.toUpperCase(),
    style: TextStyle(
      fontSize: 10,
      fontWeight: FontWeight.w700,
      color: roleColor(role),
    ),
  ),
);

/// Team detail: members with roles, pending invites, shared projects,
/// invitations, ownership transfer, leave, and delete.
class TeamDetailView extends StatefulWidget {
  const TeamDetailView({
    super.key,
    required this.api,
    required this.teamId,
    required this.actions,
    required this.onRunAction,
    required this.onChanged,
  });

  final BoardApi api;
  final int teamId;
  final List<FeatureAction> actions;
  final Future<void> Function(
    FeatureAction action, {
    Map<String, String>? pathOverrides,
  })
  onRunAction;
  final Future<void> Function() onChanged;

  @override
  State<TeamDetailView> createState() => _TeamDetailViewState();
}

class _TeamDetailViewState extends State<TeamDetailView> {
  late Future<Map<String, dynamic>> _detailFuture;
  int? _transferUserId;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _detailFuture = _load();
  }

  Future<Map<String, dynamic>> _load() async =>
      widget.api.get('/api/teams/${widget.teamId}');

  void _reload() {
    setState(() {
      _transferUserId = null;
      _detailFuture = _load();
    });
  }

  FeatureAction? _named(String label) {
    for (final action in widget.actions) {
      if (action.label == label) return action;
    }
    return null;
  }

  Future<void> _run(String label, Map<String, String> pathOverrides) async {
    final action = _named(label);
    if (action == null) return;
    await widget.onRunAction(action, pathOverrides: pathOverrides);
    if (mounted) _reload();
  }

  Future<void> _transfer() async {
    if (_transferUserId == null || _busy) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Transfer ownership?'),
        content: const Text(
          'The new owner gains full control of this team.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Transfer'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.api.post('/api/teams/${widget.teamId}/transfer', {
        'user_id': _transferUserId,
      });
      await widget.onChanged();
      if (!mounted) return;
      _reload();
    } catch (error) {
      if (!mounted) return;
      setState(
        () => _error = error.toString().replaceFirst('Exception: ', ''),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: BoardBackdrop(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 6),
                child: Row(
                  children: [
                    IconButton(
                      tooltip: 'Back to teams',
                      onPressed: () => Navigator.pop(context),
                      icon: const Icon(Icons.arrow_back_rounded),
                    ),
                    const SizedBox(width: 6),
                    const Expanded(
                      child: Text(
                        'Team',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: boardInk,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 10, 20, 24),
                  child: FutureBuilder<Map<String, dynamic>>(
                    future: _detailFuture,
                    builder: (context, snapshot) {
                      if (snapshot.connectionState != ConnectionState.done) {
                        return const Padding(
                          padding: EdgeInsets.all(48),
                          child: Center(child: CircularProgressIndicator()),
                        );
                      }
                      if (snapshot.hasError || !snapshot.hasData) {
                        return BoardSurface(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text(
                                'Could not open this team.',
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                  color: boardInk,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                '${snapshot.error ?? 'Unknown error'}'
                                    .replaceFirst('Exception: ', ''),
                                style: const TextStyle(
                                  color: boardMuted,
                                  fontSize: 13,
                                ),
                              ),
                              const SizedBox(height: 14),
                              OutlinedButton.icon(
                                onPressed: _reload,
                                icon: const Icon(
                                  Icons.refresh_rounded,
                                  size: 16,
                                ),
                                label: const Text('Retry'),
                              ),
                            ],
                          ),
                        );
                      }
                      return _TeamDetailBody(
                        detail: snapshot.data!,
                        busy: _busy,
                        error: _error,
                        transferUserId: _transferUserId,
                        onTransferUserChanged: (value) =>
                            setState(() => _transferUserId = value),
                        onTransfer: _transfer,
                        onRun: _run,
                      );
                    },
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TeamDetailBody extends StatelessWidget {
  const _TeamDetailBody({
    required this.detail,
    required this.busy,
    required this.error,
    required this.transferUserId,
    required this.onTransferUserChanged,
    required this.onTransfer,
    required this.onRun,
  });

  final Map<String, dynamic> detail;
  final bool busy;
  final String? error;
  final int? transferUserId;
  final void Function(int?) onTransferUserChanged;
  final VoidCallback onTransfer;
  final void Function(String label, Map<String, String> pathOverrides) onRun;

  @override
  Widget build(BuildContext context) {
    final team = (detail['team'] as Map?)?.cast<String, dynamic>() ?? {};
    final members =
        (detail['members'] as List?)?.whereType<Map>().toList() ?? [];
    final invites =
        (detail['invites'] as List?)?.whereType<Map>().toList() ?? [];
    final projects =
        (detail['projects'] as List?)?.whereType<Map>().toList() ?? [];
    final teamId = '${team['id'] ?? ''}';
    final myRole = team['my_role']?.toString() ?? '';
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
                      team['name']?.toString() ?? 'Team',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                        color: boardInk,
                      ),
                    ),
                  ),
                  if (myRole.isNotEmpty) _roleChip(myRole),
                ],
              ),
              if ((team['description']?.toString() ?? '').isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  team['description'].toString(),
                  style: const TextStyle(color: boardMuted, fontSize: 13),
                ),
              ],
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton(
                    onPressed: busy
                        ? null
                        : () => onRun('Edit team', {'team_id': teamId}),
                    child: const Text('Edit'),
                  ),
                  OutlinedButton(
                    onPressed: busy
                        ? null
                        : () => onRun('Invite member', {'team_id': teamId}),
                    child: const Text('Invite member'),
                  ),
                  OutlinedButton(
                    onPressed: busy
                        ? null
                        : () => onRun('Share folder', {'team_id': teamId}),
                    child: const Text('Share folder'),
                  ),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () => onRun('Leave team', {'team_id': teamId}),
                    child: const Text('Leave team'),
                  ),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () => onRun('Delete team', {'team_id': teamId}),
                    child: const Text(
                      'Delete team',
                      style: TextStyle(color: Color(0xFFB33142)),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Members (${members.length})',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
              const SizedBox(height: 8),
              for (final member in members)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              memberLabel(member.cast<String, dynamic>()),
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: boardInk,
                              ),
                            ),
                            Text(
                              'Role: ${member['role'] ?? ''}',
                              style: const TextStyle(
                                color: boardMuted,
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                      _roleChip('${member['role'] ?? ''}'),
                      const SizedBox(width: 6),
                      PopupMenuButton<String>(
                        tooltip: 'Member actions',
                        icon: const Icon(
                          Icons.more_horiz,
                          size: 18,
                          color: boardMuted,
                        ),
                        onSelected: (value) => onRun(value, {
                          'team_id': teamId,
                          'user_id': '${member['id']}',
                        }),
                        itemBuilder: (context) => const [
                          PopupMenuItem(
                            value: 'Update member',
                            child: Text('Change role'),
                          ),
                          PopupMenuItem(
                            value: 'Remove member',
                            child: Text('Remove'),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        if (invites.isNotEmpty) ...[
          const SizedBox(height: 16),
          BoardSurface(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Pending invites (${invites.length})',
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: boardInk,
                  ),
                ),
                const SizedBox(height: 8),
                for (final invite in invites)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                invite['email']?.toString() ?? 'Invite',
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: boardInk,
                                ),
                              ),
                              Text(
                                'Role: ${invite['role'] ?? ''}',
                                style: const TextStyle(
                                  color: boardMuted,
                                  fontSize: 12,
                                ),
                              ),
                            ],
                          ),
                        ),
                        TextButton(
                          onPressed: busy
                              ? null
                              : () => onRun('Revoke invitation', {
                                  'team_id': teamId,
                                  'invite_id': '${invite['id']}',
                                }),
                          child: const Text('Revoke'),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ],
        const SizedBox(height: 16),
        BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Shared projects (${projects.length})',
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
              const SizedBox(height: 8),
              if (projects.isEmpty)
                const Text(
                  'No shared folders yet.',
                  style: TextStyle(color: boardMuted, fontSize: 13),
                ),
              for (final project in projects)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              project['display_name']?.toString() ??
                                  project['name']?.toString() ??
                                  'Project',
                              style: const TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                                color: boardInk,
                              ),
                            ),
                            Text(
                              project['path']?.toString() ?? '',
                              style: const TextStyle(
                                color: boardMuted,
                                fontSize: 12,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                      TextButton(
                        onPressed: busy
                            ? null
                            : () => onRun('Unlink folder', {
                                'team_id': teamId,
                                'project_id': '${project['id']}',
                              }),
                        child: const Text('Unlink'),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        BoardSurface(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Transfer ownership',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: boardInk,
                ),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<int>(
                      initialValue: transferUserId,
                      hint: const Text('Choose a member'),
                      items: [
                        for (final member in members)
                          if (int.tryParse('${member['id']}') != null)
                            DropdownMenuItem(
                              value: int.parse('${member['id']}'),
                              child: Text(
                                memberLabel(member.cast<String, dynamic>()),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                      ],
                      onChanged: busy ? null : onTransferUserChanged,
                      decoration: const InputDecoration(
                        labelText: 'New owner',
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: busy || transferUserId == null
                        ? null
                        : onTransfer,
                    child: const Text('Transfer'),
                  ),
                ],
              ),
              if (error != null) ...[
                const SizedBox(height: 10),
                Text(
                  error!,
                  style: const TextStyle(
                    color: Color(0xFFB33142),
                    fontSize: 12,
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

