"""
Report generation for compliance audits (JSON and HTML dashboards).
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path


@dataclass
class Finding:
    """Represent a single compliance finding."""
    id: str
    file_path: str
    line_number: int
    domain: str
    severity: str
    finding_type: str
    message: str
    code_snippet: str = ""
    suggested_fix: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JSONReportGenerator:
    """Generate JSON-formatted compliance reports."""
    
    def generate(self, report, output_path: str) -> str:
        """Generate JSON report and write to file.

        Args:
            report: Dictionary or ComplianceReport dataclass
            output_path: Path where JSON report should be written

        Returns:
            Path to generated report
        """
        # Convert dataclass to dict if needed
        from dataclasses import asdict, is_dataclass
        if is_dataclass(report) and not isinstance(report, type):
            report_dict = asdict(report)
        else:
            report_dict = report

        output = {
            "timestamp": datetime.now().isoformat(),
            "report": report_dict,
            "findings": self._serialize_findings(report_dict.get('findings', [])),
            "scores": report_dict.get('scores', {}),
            "overall_grade": report_dict.get('overall_grade', 'A'),
            "summary": self._generate_summary(report_dict)
        }

        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2, default=str)

        return output_path
    
    def _serialize_findings(self, findings: List[Any]) -> List[Dict[str, Any]]:
        """Convert findings to serializable format."""
        from dataclasses import asdict, is_dataclass

        serialized = []
        for finding in findings:
            if isinstance(finding, Finding):
                serialized.append(finding.to_dict())
            elif isinstance(finding, dict):
                serialized.append(finding)
            elif is_dataclass(finding) and not isinstance(finding, type):
                # Handle Finding dataclass from base_analyzer
                serialized.append(asdict(finding))
            else:
                serialized.append({
                    'id': getattr(finding, 'id', ''),
                    'file_path': getattr(finding, 'file_path', ''),
                    'line_number': getattr(finding, 'line_number', 0),
                    'domain': getattr(finding, 'category', ''),
                    'severity': getattr(finding, 'severity', 'UNKNOWN'),
                    'message': getattr(finding, 'message', ''),
                })
        return serialized
    
    def _serialize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Ensure scores are JSON-serializable."""
        return {k: float(v) for k, v in scores.items()}
    
    def _generate_summary(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Generate overall compliance summary."""
        findings = report.get('findings', [])
        
        severity_counts = {
            'CRITICAL': 0,
            'HIGH': 0,
            'MEDIUM': 0,
            'LOW': 0
        }
        
        domain_counts = {}
        
        for finding in findings:
            severity = finding.get('severity') if isinstance(finding, dict) else getattr(finding, 'severity', 'UNKNOWN')
            domain = finding.get('domain', finding.get('category', 'unknown')) if isinstance(finding, dict) else getattr(finding, 'domain', getattr(finding, 'category', 'unknown'))
            
            if severity in severity_counts:
                severity_counts[severity] += 1
            
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        total_findings = sum(severity_counts.values())
        compliance_score = max(0.0, 1.0 - (total_findings * 0.05))
        
        return {
            'total_findings': total_findings,
            'severity_breakdown': severity_counts,
            'domain_breakdown': domain_counts,
            'overall_compliance_score': min(1.0, max(0.0, compliance_score)),
            'is_compliant': severity_counts['CRITICAL'] == 0
        }


class HTMLDashboardGenerator:
    """Generate single-page HTML compliance dashboard."""
    
    def generate(self, report: Dict[str, Any], output_path: str) -> str:
        """Generate HTML dashboard and write to file."""
        html_content = self._build_html(report)
        
        with open(output_path, 'w') as f:
            f.write(html_content)
        
        return output_path
    
    def _build_html(self, report) -> str:
        """Build complete HTML dashboard."""
        if hasattr(report, 'findings'):
            findings = report.findings
            scores = getattr(report, 'domain_scores', getattr(report, 'scores', {}))
        else:
            findings = report.get('findings', [])
            scores = report.get('scores', {})
        
        severity_breakdown = self._count_by_severity(findings)
        domain_breakdown = self._count_by_domain(findings)
        
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Compliance Audit Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            color: #333;
            margin-bottom: 10px;
        }}
        
        .header p {{
            color: #666;
            font-size: 14px;
        }}
        
        .metrics {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .metric-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }}
        
        .metric-card h3 {{
            color: #666;
            font-size: 14px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        
        .metric-card .value {{
            font-size: 32px;
            font-weight: bold;
            color: #333;
        }}
        
        .metric-card.critical {{
            border-left-color: #dc3545;
        }}
        
        .metric-card.warning {{
            border-left-color: #ffc107;
        }}
        
        .metric-card.success {{
            border-left-color: #28a745;
        }}
        
        .score-gauge {{
            display: inline-block;
            font-size: 48px;
            font-weight: bold;
        }}
        
        .score-gauge.high {{
            color: #28a745;
        }}
        
        .score-gauge.medium {{
            color: #ffc107;
        }}
        
        .score-gauge.low {{
            color: #dc3545;
        }}
        
        .section {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .section h2 {{
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }}
        
        .domain-section {{
            margin-bottom: 30px;
        }}
        
        .domain-header {{
            background: #f8f9fa;
            padding: 15px;
            border-left: 4px solid #667eea;
            margin-bottom: 15px;
            cursor: pointer;
            user-select: none;
            border-radius: 4px;
        }}
        
        .domain-header:hover {{
            background: #e9ecef;
        }}
        
        .domain-header h3 {{
            margin: 0;
            color: #333;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .domain-toggle {{
            font-size: 20px;
            color: #667eea;
        }}
        
        .findings-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .findings-table th {{
            background: #f8f9fa;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            color: #333;
            border-bottom: 2px solid #ddd;
        }}
        
        .findings-table td {{
            padding: 12px;
            border-bottom: 1px solid #eee;
        }}
        
        .findings-table tr:hover {{
            background: #f8f9fa;
        }}
        
        .severity-badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            display: inline-block;
        }}
        
        .severity-critical {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .severity-high {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .severity-medium {{
            background: #d1ecf1;
            color: #0c5460;
        }}
        
        .severity-low {{
            background: #d4edda;
            color: #155724;
        }}
        
        .findings-hidden {{
            display: none;
        }}
        
        .filter-controls {{
            margin-bottom: 20px;
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        
        .filter-btn {{
            padding: 8px 16px;
            border: 1px solid #ddd;
            border-radius: 4px;
            background: white;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.2s;
        }}
        
        .filter-btn:hover {{
            background: #f8f9fa;
        }}
        
        .filter-btn.active {{
            background: #667eea;
            color: white;
            border-color: #667eea;
        }}
        
        .footer {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            color: #666;
            font-size: 12px;
        }}
        
        @media (max-width: 768px) {{
            .metrics {{
                grid-template-columns: 1fr;
            }}
            
            .findings-table {{
                font-size: 12px;
            }}
            
            .findings-table th, .findings-table td {{
                padding: 8px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Compliance Audit Report</h1>
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="metrics">
            {self._render_metric_cards(findings, scores)}
        </div>
        
        <div class="section">
            <h2>Findings by Domain</h2>
            {self._render_filter_controls()}
            {self._render_domains(findings)}
        </div>
        
        <div class="footer">
            <p>Compliance Audit Dashboard | {datetime.now().year}</p>
        </div>
    </div>
    
    <script>
        function toggleDomain(domainName) {{
            const content = document.getElementById('content-' + domainName);
            const toggle = document.getElementById('toggle-' + domainName);
            if (content.classList.contains('findings-hidden')) {{
                content.classList.remove('findings-hidden');
                toggle.textContent = '▼';
            }} else {{
                content.classList.add('findings-hidden');
                toggle.textContent = '▶';
            }}
        }}
        
        function filterBySeverity(severity) {{
            const rows = document.querySelectorAll('[data-severity]');
            const buttons = document.querySelectorAll('.filter-btn');
            
            buttons.forEach(btn => btn.classList.remove('active'));
            
            if (severity === 'all') {{
                rows.forEach(row => row.style.display = '');
                document.querySelector('[data-filter="all"]').classList.add('active');
            }} else {{
                rows.forEach(row => {{
                    row.style.display = row.dataset.severity === severity ? '' : 'none';
                }});
                document.querySelector('[data-filter="' + severity + '"]').classList.add('active');
            }}
        }}
        
        // Initialize with 'all' severity shown
        window.addEventListener('load', () => {{
            filterBySeverity('all');
        }});
    </script>
</body>
</html>
"""
    
    def _render_metric_cards(self, findings: List[Any], scores: Dict[str, float]) -> str:
        """Render metric cards for dashboard."""
        severity_counts = self._count_by_severity(findings)
        
        overall_score = scores.get('overall', 0.85)
        score_class = 'high' if overall_score >= 0.8 else 'medium' if overall_score >= 0.6 else 'low'
        
        return f"""
        <div class="metric-card critical">
            <h3>Critical Issues</h3>
            <div class="value">{severity_counts.get('CRITICAL', 0)}</div>
        </div>
        <div class="metric-card warning">
            <h3>High Issues</h3>
            <div class="value">{severity_counts.get('HIGH', 0)}</div>
        </div>
        <div class="metric-card">
            <h3>Total Findings</h3>
            <div class="value">{sum(severity_counts.values())}</div>
        </div>
        <div class="metric-card success">
            <h3>Compliance Score</h3>
            <div class="value"><span class="score-gauge {score_class}">{overall_score:.0%}</span></div>
        </div>
        """
    
    def _render_filter_controls(self) -> str:
        """Render severity filter buttons."""
        return """
        <div class="filter-controls">
            <button class="filter-btn active" data-filter="all" onclick="filterBySeverity('all')">All Issues</button>
            <button class="filter-btn" data-filter="CRITICAL" onclick="filterBySeverity('CRITICAL')">Critical</button>
            <button class="filter-btn" data-filter="HIGH" onclick="filterBySeverity('HIGH')">High</button>
            <button class="filter-btn" data-filter="MEDIUM" onclick="filterBySeverity('MEDIUM')">Medium</button>
            <button class="filter-btn" data-filter="LOW" onclick="filterBySeverity('LOW')">Low</button>
        </div>
        """
    
    def _render_domains(self, findings: List[Any]) -> str:
        """Render findings grouped by domain."""
        domain_map = self._group_by_domain(findings)
        html = ""
        
        for domain in sorted(domain_map.keys()):
            domain_findings = domain_map[domain]
            severity_counts = self._count_severity_in_list(domain_findings)
            
            table_rows = "\n".join([
                self._render_finding_row(f) for f in domain_findings
            ])
            
            html += f"""
            <div class="domain-section">
                <div class="domain-header" onclick="toggleDomain('{domain}')">
                    <h3>
                        <span>{domain} ({len(domain_findings)})</span>
                        <span id="toggle-{domain}" class="domain-toggle">▼</span>
                    </h3>
                </div>
                <div id="content-{domain}" class="findings-hidden">
                    <table class="findings-table">
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Line</th>
                                <th>Severity</th>
                                <th>Type</th>
                                <th>Message</th>
                            </tr>
                        </thead>
                        <tbody>
                            {table_rows}
                        </tbody>
                    </table>
                </div>
            </div>
            """
        
        return html
    
    def _render_finding_row(self, finding: Any) -> str:
        """Render single finding table row."""
        if isinstance(finding, dict):
            file_path = finding.get('file_path', 'unknown')
            line_num = finding.get('line_number', 0)
            severity = finding.get('severity', 'UNKNOWN')
            finding_type = finding.get('finding_type', 'unknown')
            message = finding.get('message', '')
        else:
            file_path = getattr(finding, 'file_path', 'unknown')
            line_num = getattr(finding, 'line_number', 0)
            severity = getattr(finding, 'severity', 'UNKNOWN')
            finding_type = getattr(finding, 'finding_type', 'unknown')
            message = getattr(finding, 'message', '')
        
        severity_lower = severity.lower()
        
        return f"""
            <tr data-severity="{severity}">
                <td>{file_path}</td>
                <td>{line_num}</td>
                <td><span class="severity-badge severity-{severity_lower}">{severity}</span></td>
                <td>{finding_type}</td>
                <td>{message[:80]}{'...' if len(message) > 80 else ''}</td>
            </tr>
        """
    
    def _count_by_severity(self, findings: List[Any]) -> Dict[str, int]:
        """Count findings by severity level."""
        counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for finding in findings:
            severity = finding.get('severity') if isinstance(finding, dict) else getattr(finding, 'severity', 'UNKNOWN')
            if severity in counts:
                counts[severity] += 1
        return counts
    
    def _count_by_domain(self, findings: List[Any]) -> Dict[str, int]:
        """Count findings by domain."""
        counts = {}
        for finding in findings:
            domain = finding.get('domain', finding.get('category', 'unknown')) if isinstance(finding, dict) else getattr(finding, 'domain', getattr(finding, 'category', 'unknown'))
            counts[domain] = counts.get(domain, 0) + 1
        return counts
    
    def _group_by_domain(self, findings: List[Any]) -> Dict[str, List[Any]]:
        """Group findings by domain."""
        grouped = {}
        for finding in findings:
            domain = finding.get('domain', finding.get('category', 'unknown')) if isinstance(finding, dict) else getattr(finding, 'domain', getattr(finding, 'category', 'unknown'))
            if domain not in grouped:
                grouped[domain] = []
            grouped[domain].append(finding)
        return grouped
    
    def _count_severity_in_list(self, findings: List[Any]) -> Dict[str, int]:
        """Count severity levels in a finding list."""
        counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for finding in findings:
            severity = finding.get('severity') if isinstance(finding, dict) else getattr(finding, 'severity', 'UNKNOWN')
            if severity in counts:
                counts[severity] += 1
        return counts
