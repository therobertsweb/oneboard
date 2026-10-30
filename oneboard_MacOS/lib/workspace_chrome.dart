import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'apple_design.dart';

const workspaceNavigation = <({String title, IconData icon})>[
  (title: 'Dashboard', icon: CupertinoIcons.square_grid_2x2),
  (title: 'Studio', icon: CupertinoIcons.folder),
  (title: 'Preview', icon: CupertinoIcons.rectangle),
  (title: 'Site & Brand', icon: CupertinoIcons.globe),
  (title: 'Site Health', icon: CupertinoIcons.heart),
  (title: 'Requests', icon: CupertinoIcons.tray),
  (title: 'Calendar', icon: CupertinoIcons.calendar),
  (title: 'Alerts', icon: CupertinoIcons.bell),
  (title: 'Reports', icon: CupertinoIcons.chart_bar),
  (title: 'Social', icon: CupertinoIcons.share),
  (title: 'Security', icon: CupertinoIcons.shield),
  (title: 'Notifications', icon: CupertinoIcons.bell),
  (title: 'Settings', icon: CupertinoIcons.gear),
  (title: 'Help', icon: CupertinoIcons.question_circle),
];

class WorkspaceChrome extends StatelessWidget {
  const WorkspaceChrome({
    super.key,
    required this.userName,
    required this.selectedSection,
    required this.busy,
    required this.usingCachedData,
    required this.onLogout,
    required this.onNavigate,
    required this.onRefresh,
    required this.child,
    this.onSearch,
  });
  final String userName;
  final int selectedSection;
  final bool busy, usingCachedData;
  final VoidCallback onLogout, onRefresh;
  final ValueChanged<int> onNavigate;
  final Widget child;
  final VoidCallback? onSearch;
  @override
  Widget build(BuildContext context) => BoardBackdrop(
    child: Row(
      children: [
        _sidebar(),
        Expanded(
          child: Column(
            children: [
              _topbar(),
              Expanded(child: child),
            ],
          ),
        ),
      ],
    ),
  );

  Widget _sidebar() => Container(
    width: 232,
    padding: const EdgeInsets.fromLTRB(16, 24, 16, 18),
    decoration: BoxDecoration(
      color: Colors.white.withValues(alpha: .52),
      border: const Border(right: BorderSide(color: Color(0x0C243B70))),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(left: 7, bottom: 30),
          child: Row(
            children: [
              BoardMark(size: 36),
              SizedBox(width: 11),
              Text(
                'OneBoard',
                style: TextStyle(
                  fontSize: 21,
                  fontWeight: FontWeight.w700,
                  letterSpacing: -.9,
                  color: boardInk,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView(
            children: [
              _sidebarLabel('Workspace'),
              ...[0, 1, 2, 3, 4].map(_navItem),
              const SizedBox(height: 20),
              _sidebarLabel('Plan & collaborate'),
              ...[5, 6, 8, 9].map(_navItem),
              const SizedBox(height: 20),
              _sidebarLabel('Manage'),
              ...[7, 10, 11, 12, 13].map(_navItem),
            ],
          ),
        ),
        const SizedBox(height: 14),
        const Divider(height: 1, color: Color(0x10243B70)),
        const SizedBox(height: 16),
        Row(
          children: [
            CircleAvatar(
              radius: 18,
              backgroundColor: const Color(0xFFE4E8FC),
              child: Text(
                userName.isEmpty ? 'O' : userName[0].toUpperCase(),
                style: const TextStyle(
                  color: Color(0xFF5E66A8),
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    userName.isEmpty ? 'Your workspace' : userName,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 3),
                  const Text(
                    'Personal workspace',
                    style: TextStyle(fontSize: 10, color: boardMuted),
                  ),
                ],
              ),
            ),
            IconButton(
              tooltip: 'Sign out',
              onPressed: onLogout,
              icon: const Icon(
                Icons.logout_rounded,
                size: 16,
                color: boardMuted,
              ),
            ),
          ],
        ),
      ],
    ),
  );

  Widget _sidebarLabel(String title) => Padding(
    padding: const EdgeInsets.fromLTRB(11, 0, 0, 8),
    child: Text(
      title,
      style: const TextStyle(
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: Color(0xFF979CAE),
      ),
    ),
  );

  Widget _navItem(int index) {
    final selected = selectedSection == index;
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Material(
        color: selected ? Colors.white : Colors.transparent,
        elevation: selected ? 1 : 0,
        shadowColor: const Color(0x18243B70),
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          onTap: busy ? null : () => onNavigate(index),
          borderRadius: BorderRadius.circular(10),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 10),
            child: Row(
              children: [
                Icon(
                  workspaceNavigation[index].icon,
                  size: 18,
                  color: selected ? boardBlue : const Color(0xFF82899E),
                ),
                const SizedBox(width: 11),
                Expanded(
                  child: Text(
                    workspaceNavigation[index].title,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                      color: selected ? boardBlue : const Color(0xFF5D6479),
                    ),
                  ),
                ),
                if (selected)
                  Container(
                    width: 5,
                    height: 5,
                    decoration: const BoxDecoration(
                      color: boardBlue,
                      shape: BoxShape.circle,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _topbar() => Container(
    height: 62,
    padding: const EdgeInsets.symmetric(horizontal: 32),
    decoration: const BoxDecoration(
      border: Border(bottom: BorderSide(color: Color(0x08243B70))),
    ),
    child: Row(
      children: [
        const Icon(Icons.window_outlined, size: 17, color: boardMuted),
        const SizedBox(width: 12),
        const Text(
          'Workspace',
          style: TextStyle(color: boardMuted, fontSize: 12),
        ),
        const Padding(
          padding: EdgeInsets.symmetric(horizontal: 10),
          child: Icon(Icons.chevron_right, size: 14, color: Color(0xFFB8BDCA)),
        ),
        Text(
          workspaceNavigation[selectedSection].title,
          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
        const Spacer(),
        if (usingCachedData)
          const Padding(
            padding: EdgeInsets.only(right: 12),
            child: Text(
              'Offline copy',
              style: TextStyle(color: boardMuted, fontSize: 11),
            ),
          ),
        if (onSearch != null)
          IconButton(
            tooltip: 'Search (⌘K)',
            onPressed: busy ? null : onSearch,
            icon: const Icon(
              CupertinoIcons.search,
              size: 19,
              color: boardMuted,
            ),
          ),
        if (onSearch != null) const SizedBox(width: 4),
        IconButton(
          tooltip: 'Refresh',
          onPressed: busy ? null : onRefresh,
          icon: const Icon(
            CupertinoIcons.arrow_clockwise,
            size: 19,
            color: boardMuted,
          ),
        ),
        const SizedBox(width: 4),
        IconButton(
          tooltip: 'Notifications',
          onPressed: () => onNavigate(11),
          icon: const Icon(CupertinoIcons.bell, size: 20, color: boardMuted),
        ),
      ],
    ),
  );
}
