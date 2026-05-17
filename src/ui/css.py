"""程序说明：UI 样式常量。"""

UI_CSS = UI_CSS = """
/* 最近质检记录表格列宽优化 */
#quality-recent-table table { table-layout: fixed !important; width: 100% !important; }
#quality-recent-table table th:nth-child(1),
#quality-recent-table table td:nth-child(1) { width: 4% !important; text-align: center; }
#quality-recent-table table th:nth-child(2),
#quality-recent-table table td:nth-child(2) { width: 18% !important; }
#quality-recent-table table th:nth-child(3),
#quality-recent-table table td:nth-child(3) { width: 10% !important; }
#quality-recent-table table th:nth-child(4),
#quality-recent-table table td:nth-child(4) { width: 8% !important; }
#quality-recent-table table th:nth-child(5),
#quality-recent-table table td:nth-child(5) { width: 6% !important; text-align: center; }
#quality-recent-table table th:nth-child(6),
#quality-recent-table table td:nth-child(6) { width: 8% !important; text-align: center; }
#quality-recent-table table th:nth-child(7),
#quality-recent-table table td:nth-child(7) { width: 14% !important; }
#quality-recent-table table th:nth-child(8),
#quality-recent-table table td:nth-child(8) { width: 32% !important; overflow: hidden; text-overflow: ellipsis; }

#search-top-row {
  align-items: stretch !important;
  gap: 12px !important;
}
#search-top-row > .gradio-column,
#search-result-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#document-management-top-row,
#document-management-summary-row,
#document-management-focus-row {
  align-items: stretch !important;
  gap: 14px !important;
}
#document-management-top-row > .gradio-column,
#document-management-summary-row > .gradio-column,
#document-management-focus-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#document-management-help-panel,
#document-management-selector-panel,
#document-summary-panel,
#database-summary-panel {
  height: 100%;
}
#document-management-selector-panel,
#document-summary-panel,
#database-summary-panel,
#document-register-result,
#document-rebuild-result,
#document-quality-report,
#document-quality-checks,
#document-quality-search-summary,
#document-quality-search-detail,
#document-quality-batch-summary,
#document-quality-config-panel,
#document-quality-config-result {
  margin-top: 0;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 28%),
    var(--block-background-fill);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
#document-management-help-panel,
#document-summary-panel,
#database-summary-panel,
#document-register-result,
#document-rebuild-result,
#document-quality-report,
#document-quality-checks,
#document-quality-search-summary,
#document-quality-search-detail,
#document-quality-batch-summary,
#document-quality-config-panel,
#document-quality-config-result {
  margin-top: 0;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#document-management-help-panel,
#document-management-selector-panel {
  min-height: 188px;
}
#document-summary-panel > div,
#database-summary-panel > div {
  height: 100%;
}
#document-current-panel,
#document-quality-panel {
  width: 100%;
}
#document-current-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 28%),
    var(--block-background-fill);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
  overflow: hidden;
  padding: 18px 20px;
}
#document-current-panel > div,
#document-quality-panel > div,
#database-summary-table-panel > div,
#document-list-panel > div,
#document-quality-batch-panel > div,
#document-quality-result-panel > div {
  height: 100%;
}
#document-current-title {
  margin: 0 0 4px 0 !important;
  text-align: left !important;
  font-size: 20px !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
}
#document-current-note {
  margin: 0 0 8px 0 !important;
  font-size: 13px !important;
  line-height: 1.7 !important;
  color: var(--body-text-color-subdued) !important;
}
#document-current-panel .gradio-dropdown label,
#document-current-panel .gradio-dropdown .wrap label,
#document-current-panel .gradio-dropdown .label-wrap {
  font-weight: 700 !important;
}
#document-current-panel .gradio-dropdown input,
#document-current-panel .gradio-dropdown button,
#document-current-panel .gradio-dropdown .wrap {
  border-color: rgba(96, 165, 250, 0.38) !important;
}
#document-current-detail {
  margin-top: 4px;
}
#document-current-detail > div {
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  padding: 0 !important;
}
#document-current-detail h3,
#document-current-detail h4 {
  margin-top: 6px !important;
  margin-bottom: 8px !important;
  font-size: 15px !important;
}
#document-current-detail p,
#document-current-detail li {
  font-size: 13px !important;
  line-height: 1.65 !important;
}
#document-current-detail ul {
  margin-top: 6px !important;
  margin-bottom: 0 !important;
  padding-left: 18px !important;
}
#document-quality-accordion button,
#document-quality-accordion summary {
  justify-content: center !important;
  text-align: center !important;
  min-height: 56px !important;
  padding-top: 10px !important;
  padding-bottom: 10px !important;
  font-size: 20px !important;
  font-weight: 700 !important;
  letter-spacing: 0.04em;
  border-radius: 18px !important;
  border: 1px solid rgba(148, 163, 184, 0.18) !important;
  border-bottom: 1px solid rgba(96, 165, 250, 0.28) !important;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06) !important;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 30%),
    var(--block-background-fill) !important;
}
#document-quality-accordion button span,
#document-quality-accordion summary span {
  width: 100%;
  text-align: center !important;
}
#document-quality-accordion {
  margin-top: 10px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  padding-top: 10px;
}
#document-quality-panel {
  padding-top: 6px;
}
#document-current-actions-row,
#database-pagination-row,
#document-pagination-row,
#document-management-actions-row,
#document-management-result-row,
#document-quality-sections-pagination-row,
#document-quality-chunks-pagination-row,
#document-quality-search-pagination-row,
#document-quality-batch-pagination-row {
  gap: 10px !important;
  margin-top: 6px !important;
}
#document-pagination-row {
  margin-top: 4px !important;
}
#document-page-info {
  margin-top: 2px !important;
}
#document-management-actions-row,
#document-management-result-row,
#document-quality-summary-row,
#document-quality-sample-row,
#document-quality-search-row,
#document-quality-result-row,
#document-quality-batch-row,
#document-quality-config-row {
  align-items: stretch !important;
  gap: 14px !important;
}
#document-management-actions-row > .gradio-column,
#document-management-result-row > .gradio-column,
#document-quality-summary-row > .gradio-column,
#document-quality-sample-row > .gradio-column,
#document-quality-search-row > .gradio-column,
#document-quality-result-row > .gradio-column,
#document-quality-batch-row > .gradio-column,
#document-quality-config-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#document-management-actions-row {
  display: flex !important;
  flex-wrap: wrap !important;
  margin-top: 10px !important;
  justify-content: flex-start !important;
  gap: 12px !important;
}
#document-current-actions-row {
  display: flex !important;
  flex-wrap: wrap !important;
  margin-top: 10px !important;
  justify-content: flex-start !important;
  gap: 12px !important;
}
#document-current-actions-row > * {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#document-management-actions-row > * {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#document-management-result-row {
  margin-top: 8px !important;
}
#document-management-result-row > * {
  flex: 1 1 320px !important;
}
#document-register-result,
#document-rebuild-result {
  min-height: 96px;
  height: 100%;
}
#document-quality-report,
#document-quality-checks {
  min-height: 152px;
}
#document-quality-search-summary {
  min-height: 136px;
}
#document-quality-search-detail,
#document-quality-config-panel,
#document-quality-config-result {
  min-height: 132px;
}
#document-quality-report,
#document-quality-checks,
#document-quality-search-summary,
#document-quality-search-detail,
#document-quality-config-panel,
#document-quality-config-result {
  height: 100%;
}
#document-quality-top-actions,
#document-quality-batch-action-row,
#document-quality-config-action-row {
  align-items: center !important;
  gap: 10px;
}
#document-quality-top-actions,
#document-quality-search-action-row,
#document-quality-batch-action-row,
#document-quality-config-action-row {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: stretch !important;
  gap: 10px !important;
  justify-content: flex-start !important;
}
#document-quality-top-actions > *,
#document-quality-search-action-row > *,
#document-quality-batch-action-row > *,
#document-quality-config-action-row > * {
  flex: 0 0 auto !important;
  width: auto !important;
  min-width: 0 !important;
}
#database-pagination-row,
#document-pagination-row,
#document-quality-sections-pagination-row,
#document-quality-chunks-pagination-row,
#document-quality-search-pagination-row,
#document-quality-batch-pagination-row,
#search-pagination-row,
#quality-claim-pagination-row,
#quality-evidence-pagination-row,
#quality-recent-pagination-row,
#quality-evaluation-pagination-row,
#review-pending-pagination-row,
#review-processed-pagination-row,
#review-evidence-pagination-row,
#review-history-pagination-row,
#settings-pagination-row,
#settings-knowledge-base-pagination-row {
  justify-content: flex-start !important;
}
#database-pagination-row > *,
#document-pagination-row > *,
#document-quality-sections-pagination-row > *,
#document-quality-chunks-pagination-row > *,
#document-quality-search-pagination-row > *,
#document-quality-batch-pagination-row > *,
#search-pagination-row > *,
#review-pending-pagination-row > *,
#review-processed-pagination-row > *,
#review-evidence-pagination-row > *,
#review-history-pagination-row > *,
#settings-pagination-row > *,
#settings-knowledge-base-pagination-row > * {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#document-management-help-panel > div,
#document-summary-panel > div,
#database-summary-panel > div,
#document-register-result > div,
#document-rebuild-result > div,
#document-quality-report > div,
#document-quality-checks > div,
#document-quality-search-summary > div,
#document-quality-search-detail > div,
#document-quality-batch-summary > div,
#document-quality-config-panel > div,
#document-quality-config-result > div {
  width: 100%;
  border-left: none !important;
  padding-left: 0 !important;
}
#settings-export-row,
#quality-export-row,
#search-export-row {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: flex-start !important;
  gap: 12px !important;
}
#settings-export-row {
  margin-top: 0 !important;
  justify-content: flex-end !important;
  padding: 0 !important;
}
#settings-export-row > *,
#quality-export-row > *,
#search-export-row > * {
  min-width: 0 !important;
}
#search-export-row,
#quality-export-row {
  justify-content: flex-start !important;
  gap: 10px !important;
}
#settings-export-result,
#quality-export-result,
#search-export-result {
  flex: 1 0 100% !important;
  width: 100% !important;
}
#document-quality-export-result,
#document-quality-search-export-result,
#document-quality-csv-export-result,
#document-quality-batch-export-result,
#document-quality-config-export-result {
  min-height: 72px;
}
/* 按钮规范：Gradio 直接在 <button> 上挂 elem_classes，所以选择器直接用 button.ui-button。 */
button.ui-button {
  display: inline-flex !important;
  flex: 0 0 auto !important;
  width: fit-content !important;
  min-width: 132px !important;
  max-width: 100% !important;
  align-self: flex-start !important;
  min-height: 42px !important;
  padding: 0 18px !important;
  border-radius: 14px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background:
    linear-gradient(180deg, rgba(71, 85, 105, 0.26), rgba(51, 65, 85, 0.18)) !important;
  color: var(--body-text-color) !important;
  font-weight: 700 !important;
  font-size: 14px !important;
  letter-spacing: 0.02em !important;
  box-shadow:
    0 8px 18px rgba(15, 23, 42, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
    box-shadow 0.18s ease !important;
  cursor: pointer !important;
  margin: 4px 2px !important;
}
button.ui-button:hover {
  transform: translateY(-1px) !important;
  border-color: rgba(96, 165, 250, 0.34) !important;
  background:
    linear-gradient(180deg, rgba(71, 85, 105, 0.34), rgba(51, 65, 85, 0.24)) !important;
  box-shadow:
    0 10px 22px rgba(15, 23, 42, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
}
button.ui-button:active {
  transform: scale(0.98) !important;
}
button.ui-button:focus-visible {
  outline: none !important;
  border-color: rgba(96, 165, 250, 0.42) !important;
  box-shadow:
    0 0 0 3px rgba(59, 130, 246, 0.12),
    0 10px 22px rgba(15, 23, 42, 0.14) !important;
}
button.ui-button:disabled {
  opacity: 0.6 !important;
  cursor: not-allowed !important;
  transform: none !important;
  box-shadow: none !important;
}
button.ui-button--primary {
  border-color: rgba(96, 165, 250, 0.38) !important;
  background:
    linear-gradient(180deg, rgba(59, 130, 246, 0.88), rgba(37, 99, 235, 0.82)) !important;
  color: #eff6ff !important;
  box-shadow:
    0 10px 22px rgba(37, 99, 235, 0.20),
    inset 0 1px 0 rgba(255, 255, 255, 0.10) !important;
}
button.ui-button--danger {
  border-color: rgba(248, 113, 113, 0.28) !important;
  background:
    linear-gradient(180deg, rgba(127, 29, 29, 0.88), rgba(153, 27, 27, 0.78)) !important;
  color: #fee2e2 !important;
  box-shadow:
    0 10px 22px rgba(127, 29, 29, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
}
button.ui-button--pagination {
  min-width: 96px !important;
  min-height: 38px !important;
  padding: 0 14px !important;
  border-radius: 12px !important;
  border-color: rgba(148, 163, 184, 0.2) !important;
  background: rgba(51, 65, 85, 0.12) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 4px 12px rgba(15, 23, 42, 0.06) !important;
}
#document-quality-export-result,
#document-quality-search-export-result,
#document-quality-csv-export-result,
#document-quality-batch-export-result,
#document-quality-export-result *,
#document-quality-search-export-result *,
#document-quality-csv-export-result *,
#document-quality-batch-export-result *,
#document-quality-config-export-result * {
  max-width: 100% !important;
  box-sizing: border-box !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
#document-quality-search-export-result,
#document-quality-csv-export-result,
#document-quality-batch-export-result,
#document-quality-config-export-result {
  margin-top: 4px !important;
}
#document-quality-result-row,
#document-quality-batch-row,
#document-quality-config-row {
  margin-top: 6px !important;
}
#document-quality-batch-summary {
  min-height: 104px;
}
#document-quality-sections-page-info,
#document-quality-chunks-page-info,
#document-quality-search-page-info,
#document-quality-batch-page-info {
  margin-top: 2px !important;
}
#database-page-info > div,
#document-page-info > div,
#document-quality-sections-page-info > div,
#document-quality-chunks-page-info > div,
#document-quality-search-page-info > div,
#document-quality-batch-page-info > div {
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.04);
  color: var(--body-text-color-subdued);
}
#document-quality-config-form {
  padding: 12px !important;
}
#document-quality-config-form > .gradio-markdown {
  margin-bottom: 4px !important;
}
#document-quality-config-form .gr-block.gr-box {
  border: none !important;
  box-shadow: none !important;
}
#document-quality-config-form-row-1,
#document-quality-config-form-row-2,
#document-quality-config-form-row-3,
#document-quality-config-form-row-4 {
  gap: 8px !important;
  margin-top: 6px !important;
}
#document-quality-config-form-row-1 > *,
#document-quality-config-form-row-2 > *,
#document-quality-config-form-row-3 > *,
#document-quality-config-form-row-4 > * {
  flex: 1 1 240px !important;
  min-width: 0 !important;
}
#document-quality-config-form-row-4 > * {
  flex-basis: 100% !important;
}
#document-quality-batch-row,
#document-quality-search-row {
  gap: 14px !important;
}
#document-quality-batch-row > .gradio-column,
#document-quality-search-row > .gradio-column {
  min-width: 0 !important;
}
#document-management-top-row .gradio-dropdown > div,
#document-management-focus-row .gradio-dropdown > div,
#document-quality-config-form .gradio-dropdown > div,
#document-quality-config-form textarea,
#document-quality-config-form input {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background: rgba(148, 163, 184, 0.04) !important;
}
#settings-export-result,
#settings-export-result * {
  max-width: 100% !important;
  box-sizing: border-box !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
#search-result-workspace,
#quality-main-workspace,
#quality-followup-workspace,
#review-focus-panel,
#settings-overview-panel,
#settings-workspace-panel,
#settings-footer-panel {
  margin-top: 12px;
  padding: 0;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
#search-result-workspace > div,
#quality-main-workspace > div,
#quality-followup-workspace > div,
#review-focus-panel > div,
#settings-overview-panel > div,
#settings-workspace-panel > div,
#settings-footer-panel > div {
  width: 100%;
}
#search-input-panel,
#search-help-panel {
  height: 100%;
  min-height: 184px;
  align-self: stretch !important;
}
#search-input-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 28%),
    var(--block-background-fill);
  border-radius: 22px;
  padding: 18px;
  min-height: 204px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  box-sizing: border-box;
  gap: 12px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
#search-input-panel > div,
#search-help-panel > div {
  height: 100%;
}
#search-input-panel .gradio-container-3-42-0,
#search-input-panel .gradio-container-4-44-1 {
  background: transparent !important;
}
#search-input-panel button.ui-button,
#quality-input-panel button.ui-button {
  margin-top: 6px;
}
#search-result-workspace {
  margin-top: 10px;
}
#search-pagination-row {
  margin-top: 8px !important;
  gap: 10px !important;
  flex-wrap: wrap !important;
}
#search-page-info {
  margin-top: 2px !important;
}
#search-export-row {
  margin-top: 0 !important;
}
#quality-top-row {
  align-items: stretch !important;
  gap: 14px !important;
}
#quality-top-row > .gradio-column,
#quality-template-row > .gradio-column,
#quality-summary-row > .gradio-column,
#quality-claim-row > .gradio-column,
#quality-evaluation-action-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#quality-template-row,
#quality-summary-row,
#quality-claim-row {
  align-items: stretch !important;
  gap: 14px !important;
  margin-top: 8px !important;
}
#quality-input-panel {
  min-height: 260px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  box-sizing: border-box;
}
#quality-input-panel,
#quality-help-panel,
#quality-template-panel,
#quality-progress-panel,
#quality-result-panel,
#quality-claim-list-panel,
#quality-claim-detail,
#quality-evidence-list-panel,
#quality-evidence-detail,
#quality-history-panel,
#quality-action-panel,
#quality-evaluation-panel {
  margin-top: 0;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.06), transparent 28%),
    var(--block-background-fill);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
#quality-help-panel,
#quality-template-panel,
#quality-progress-panel,
#quality-result-panel,
#quality-claim-detail,
#quality-evidence-detail,
#quality-history-panel,
#quality-action-panel,
#quality-evaluation-panel {
  height: 100%;
}
#quality-help-panel {
  min-height: 260px;
}
#quality-template-panel {
  width: 100%;
}
#quality-evaluation-action-row {
  align-items: stretch !important;
  gap: 10px !important;
}
#quality-template-panel > div,
#quality-help-panel > div,
#quality-progress-panel > div,
#quality-result-panel > div,
#quality-claim-detail > div,
#quality-evidence-detail > div {
  height: 100%;
}
#quality-history-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
#quality-input-panel,
#quality-history-panel > div {
  height: auto !important;
}
#quality-history-note {
  font-size: 13px !important;
  line-height: 1.7 !important;
  color: var(--body-text-color-subdued) !important;
  margin: 0 !important;
  padding: 12px 14px;
  border: 1px dashed rgba(148, 163, 184, 0.24);
  border-radius: 14px;
  background: rgba(148, 163, 184, 0.04);
}
#quality-input-panel button.ui-button {
  margin-top: 8px;
}
#quality-input-panel textarea,
#quality-evaluation-panel textarea {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background: rgba(148, 163, 184, 0.05) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
#quality-input-panel textarea:focus,
#quality-evaluation-panel textarea:focus {
  border-color: rgba(59, 130, 246, 0.42) !important;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.10) !important;
}
#quality-input-panel .gradio-dropdown,
#quality-history-scope,
#quality-evaluation-panel .gradio-dropdown {
  border-radius: 16px !important;
}
#quality-history-scope {
  margin-top: 2px !important;
  margin-bottom: 0 !important;
}
#quality-input-panel .gradio-dropdown > div,
#quality-history-scope > div,
#quality-evaluation-panel .gradio-dropdown > div {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background: rgba(148, 163, 184, 0.04) !important;
}
#quality-history-panel .gradio-markdown,
#quality-history-note,
#quality-recent-table {
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
#quality-input-panel label,
#quality-evaluation-panel label,
#quality-history-panel label {
  font-size: 13px !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em;
}
#quality-active-check {
  margin-bottom: 10px;
}
#quality-active-check > div {
  border: 1px solid rgba(245, 158, 11, 0.24);
  border-radius: 18px;
  background: rgba(245, 158, 11, 0.08);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}
#quality-claims-table {
  min-height: 220px;
}
#quality-claims-table label {
  display: block;
  margin-bottom: 8px !important;
  padding: 12px 14px !important;
  border: 1px solid rgba(148, 163, 184, 0.20);
  border-radius: 16px;
  background: rgba(148, 163, 184, 0.04);
  transition: border-color 0.18s ease, background 0.18s ease, transform 0.18s ease;
}
#quality-claims-table label:hover {
  border-color: rgba(59, 130, 246, 0.28);
  background: rgba(59, 130, 246, 0.06);
  transform: translateY(-1px);
}
#quality-claims-table label:has(input:checked) {
  border-color: rgba(59, 130, 246, 0.42);
  background: rgba(59, 130, 246, 0.10);
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.06);
}
#quality-evidence-table,
#quality-recent-table {
  min-height: 148px;
}
#quality-claims-table > div,
#quality-claims-table > div > div,
#quality-claims-table > div > div > div,
#quality-evidence-table > div,
#quality-evidence-table > div > div,
#quality-evidence-table > div > div > div,
#quality-recent-table > div,
#quality-recent-table > div > div,
#quality-recent-table > div > div > div {
  min-height: 0 !important;
}
#quality-claims-table table td,
#quality-recent-table table td,
#quality-evidence-table table td {
  font-size: 14px !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
  line-height: 1.7 !important;
  vertical-align: top !important;
}
#quality-claims-table table,
#quality-evidence-table table,
#quality-recent-table table,
#review-evidence-table table {
  width: 100% !important;
  table-layout: fixed !important;
}
#quality-recent-table table td:nth-child(2),
#quality-recent-table table th:nth-child(2) {
  width: 54px !important;
  min-width: 54px !important;
  text-align: center !important;
}
#quality-recent-table table td:nth-child(2) {
  font-weight: 700 !important;
  color: #b45309 !important;
}
#quality-claims-table,
#quality-evidence-table,
#quality-recent-table,
#quality-evaluation-table {
  margin-top: 6px !important;
}
#quality-claims-table table th,
#quality-evidence-table table th,
#quality-recent-table table th,
#quality-evaluation-table table th {
  font-size: 12px !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgba(148, 163, 184, 0.06) !important;
}
#quality-evidence-table table td,
#quality-recent-table table td,
#quality-evaluation-table table td {
  background: transparent !important;
}
#quality-evidence-table table tbody tr:hover td,
#quality-recent-table table tbody tr:hover td,
#quality-evaluation-table table tbody tr:hover td {
  background: rgba(148, 163, 184, 0.06) !important;
}
#quality-recent-table tr:has(td:nth-child(2) button:not(:empty)) td,
#quality-recent-table tr:has(td:nth-child(2):not(:empty)) td {
  background: rgba(245, 158, 11, 0.08) !important;
}
#quality-recent-table tr:has(td:nth-child(2) button:not(:empty)) td:first-child,
#quality-recent-table tr:has(td:nth-child(2):not(:empty)) td:first-child {
  box-shadow: inset 5px 0 0 0 rgba(245, 158, 11, 0.58) !important;
}
#quality-claims-table button[aria-label="Select column"],
#quality-claims-table button[aria-label="Select row"],
#quality-evidence-table button[aria-label="Select column"],
#quality-evidence-table button[aria-label="Select row"],
#quality-recent-table button[aria-label="Select column"],
#quality-recent-table button[aria-label="Select row"] {
  display: none !important;
}
#quality-claims-table tr:has(td:focus-within) td,
#quality-claims-table tr:has(button:focus) td,
#quality-claims-table tr:has(.selected) td,
#quality-claims-table td.selected,
#quality-evidence-table tr:has(td:focus-within) td,
#quality-evidence-table tr:has(button:focus) td,
#quality-evidence-table tr:has(.selected) td,
#quality-evidence-table td.selected,
#quality-recent-table tr:has(td:focus-within) td,
#quality-recent-table tr:has(button:focus) td,
#quality-recent-table tr:has(.selected) td,
#quality-recent-table td.selected {
  background: rgba(127, 127, 127, 0.16) !important;
}
#quality-claims-table tr:has(td:focus-within) td:first-child,
#quality-claims-table tr:has(button:focus) td:first-child,
#quality-claims-table tr:has(.selected) td:first-child,
#quality-evidence-table tr:has(td:focus-within) td:first-child,
#quality-evidence-table tr:has(button:focus) td:first-child,
#quality-evidence-table tr:has(.selected) td:first-child,
#quality-recent-table tr:has(td:focus-within) td:first-child,
#quality-recent-table tr:has(button:focus) td:first-child,
#quality-recent-table tr:has(.selected) td:first-child {
  box-shadow: inset 5px 0 0 0 rgba(127, 127, 127, 0.62) !important;
}
#quality-claims-table tr:has(td:focus-within) td,
#quality-claims-table tr:has(button:focus) td,
#quality-evidence-table tr:has(td:focus-within) td,
#quality-evidence-table tr:has(button:focus) td,
#quality-recent-table tr:has(td:focus-within) td,
#quality-recent-table tr:has(button:focus) td {
  font-weight: 600 !important;
}
#quality-evidence-detail,
#review-evidence-detail,
#quality-export-result {
  max-width: 100% !important;
  overflow: hidden !important;
}
#quality-evidence-detail {
  min-height: 136px;
}
#quality-action-panel {
  min-height: 136px;
  gap: 12px !important;
}
#quality-help-panel > div,
#quality-template-panel > div,
#quality-progress-panel > div,
#quality-result-panel > div,
#quality-claim-detail > div,
#quality-evidence-detail > div,
#quality-evaluation-help > div,
#quality-evaluation-summary > div,
#quality-export-result > div,
#quality-evaluation-export-result > div {
  border-left: none !important;
  padding-left: 0 !important;
}
#quality-export-row,
#quality-claim-pagination-row,
#quality-evidence-pagination-row,
#quality-recent-pagination-row,
#quality-evaluation-pagination-row {
  gap: 12px !important;
  flex-wrap: wrap !important;
  margin-top: 8px !important;
}
#quality-export-row > *,
#quality-claim-pagination-row > *,
#quality-evidence-pagination-row > *,
#quality-recent-pagination-row > *,
#quality-evaluation-pagination-row > * {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#quality-evaluation-action-row > .gradio-column:first-child {
  flex: 0 0 220px !important;
  max-width: 220px !important;
}
#quality-evaluation-action-row > .gradio-column:last-child {
  flex: 1 1 320px !important;
}
#quality-input-panel .gradio-row,
#quality-action-panel .gradio-row {
  gap: 10px !important;
}
#quality-evidence-detail *,
#review-evidence-detail *,
#quality-export-result * {
  max-width: 100% !important;
  box-sizing: border-box !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
#quality-export-result a {
  white-space: normal !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
#quality-claim-page-info,
#quality-evidence-page-info,
#quality-recent-page-info,
#quality-evaluation-page-info {
  margin-top: 2px !important;
}
#quality-claim-page-info > div,
#quality-evidence-page-info > div,
#quality-recent-page-info > div,
#quality-evaluation-page-info > div {
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.04);
  color: var(--body-text-color-subdued);
}
#quality-evaluation-accordion {
  margin-top: 10px !important;
}
#quality-evaluation-accordion > div {
  border: 1px solid rgba(148, 163, 184, 0.18) !important;
  border-radius: 22px !important;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 30%),
    var(--block-background-fill) !important;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
#quality-evaluation-accordion summary {
  padding: 14px 18px !important;
  font-weight: 700 !important;
}
#review-top-row {
  align-items: stretch !important;
  gap: 14px !important;
}
#review-filter-row {
  align-items: stretch !important;
  gap: 10px !important;
  flex-wrap: wrap !important;
  margin-bottom: 8px !important;
}
#review-filter-row > * {
  flex: 1 1 200px !important;
  min-width: 0 !important;
}
#review-summary-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#review-summary-row {
  align-items: stretch !important;
  gap: 12px !important;
  margin-top: 6px !important;
}
#review-focus-panel {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
}
#review-help-panel,
#review-claim-detail,
#review-record-detail,
#review-evidence-detail,
#review-pending-panel,
#review-processed-panel,
#review-evidence-list-panel,
#review-history-panel,
#review-action-panel,
#review-result-panel,
#review-export-result {
  margin-top: 0;
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.05), transparent 28%),
    var(--block-background-fill);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.05);
}
#review-action-panel {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  box-sizing: border-box;
  gap: 14px;
  min-height: 0;
  padding: 20px !important;
}
#review-action-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
#review-action-buttons {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 0;
  padding-top: 4px;
}
#review-action-feedback-row {
  display: flex;
  align-items: flex-start !important;
  gap: 10px !important;
}
#review-action-feedback-row > .gradio-column {
  align-self: flex-start !important;
}
#review-action-feedback-row .gradio-html {
  height: auto;
}
#review-help-panel,
#review-claim-detail,
#review-record-detail,
#review-evidence-detail {
  height: auto;
}
#review-help-panel > div,
#review-claim-detail > div,
#review-record-detail > div,
#review-evidence-detail > div {
  height: auto;
}
#review-help-panel {
  min-height: 152px;
}
#review-result-panel {
  min-height: 72px;
}
#review-export-result {
  min-height: 72px;
}
#review-pending-pagination-row,
#review-processed-pagination-row,
#review-evidence-pagination-row,
#review-history-pagination-row {
  margin-top: 6px !important;
  gap: 10px !important;
  flex-wrap: wrap !important;
  justify-content: flex-start !important;
}
#review-action-buttons {
  display: flex !important;
  align-items: center !important;
  gap: 12px !important;
  flex-wrap: wrap !important;
  margin: 0 !important;
  padding-top: 6px !important;
}
#review-action-buttons > * {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#review-pending-table table th,
#review-pending-table table td,
#review-processed-table table th,
#review-processed-table table td,
#review-history-table table th,
#review-history-table table td,
#review-evidence-table table th,
#review-evidence-table table td {
  font-size: 14px !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
  line-height: 1.7 !important;
  vertical-align: top !important;
}
#review-pending-table table th,
#review-processed-table table th,
#review-history-table table th,
#review-evidence-table table th {
  font-size: 12px !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgba(148, 163, 184, 0.06) !important;
}
#review-pending-table table tbody tr,
#review-processed-table table tbody tr,
#review-history-table table tbody tr,
#review-evidence-table table tbody tr {
  transition: background 0.2s ease, box-shadow 0.2s ease;
}
#review-pending-table table tbody tr:hover td,
#review-processed-table table tbody tr:hover td,
#review-history-table table tbody tr:hover td,
#review-evidence-table table tbody tr:hover td {
  background: rgba(148, 163, 184, 0.06) !important;
}
#review-pending-table button[aria-label="Select column"],
#review-pending-table button[aria-label="Select row"],
#review-processed-table button[aria-label="Select column"],
#review-processed-table button[aria-label="Select row"],
#review-history-table button[aria-label="Select column"],
#review-history-table button[aria-label="Select row"],
#review-evidence-table button[aria-label="Select column"],
#review-evidence-table button[aria-label="Select row"] {
  display: none !important;
}
#review-pending-table tr:has(td:focus-within) td,
#review-pending-table tr:has(button:focus) td,
#review-pending-table tr:has(.selected) td,
#review-pending-table td.selected,
#review-processed-table tr:has(td:focus-within) td,
#review-processed-table tr:has(button:focus) td,
#review-processed-table tr:has(.selected) td,
#review-processed-table td.selected,
#review-history-table tr:has(td:focus-within) td,
#review-history-table tr:has(button:focus) td,
#review-history-table tr:has(.selected) td,
#review-history-table td.selected,
#review-evidence-table tr:has(td:focus-within) td,
#review-evidence-table tr:has(button:focus) td,
#review-evidence-table tr:has(.selected) td,
#review-evidence-table td.selected {
  background: rgba(127, 127, 127, 0.16) !important;
  box-shadow: inset 0 1px 0 0 rgba(127, 127, 127, 0.22), inset 0 -1px 0 0 rgba(127, 127, 127, 0.22);
}
#review-pending-table tr:has(td:focus-within) td:first-child,
#review-pending-table tr:has(button:focus) td:first-child,
#review-pending-table tr:has(.selected) td:first-child,
#review-processed-table tr:has(td:focus-within) td:first-child,
#review-processed-table tr:has(button:focus) td:first-child,
#review-processed-table tr:has(.selected) td:first-child,
#review-history-table tr:has(td:focus-within) td:first-child,
#review-history-table tr:has(button:focus) td:first-child,
#review-history-table tr:has(.selected) td:first-child,
#review-evidence-table tr:has(td:focus-within) td:first-child,
#review-evidence-table tr:has(button:focus) td:first-child,
#review-evidence-table tr:has(.selected) td:first-child {
  box-shadow: inset 6px 0 0 0 rgba(59, 130, 246, 0.52) !important;
}
#review-pending-table tr:has(td:focus-within) td,
#review-pending-table tr:has(button:focus) td,
#review-processed-table tr:has(td:focus-within) td,
#review-processed-table tr:has(button:focus) td,
#review-history-table tr:has(td:focus-within) td,
#review-history-table tr:has(button:focus) td,
#review-evidence-table tr:has(td:focus-within) td,
#review-evidence-table tr:has(button:focus) td {
  font-weight: 700 !important;
}
#review-filter-row .gradio-dropdown > div,
#review-action-form .gradio-dropdown > div,
#review-action-form textarea {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background: rgba(148, 163, 184, 0.04) !important;
}
#review-action-form textarea:focus {
  border-color: rgba(59, 130, 246, 0.42) !important;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.10) !important;
}
#review-filter-row label,
#review-action-form label {
  font-size: 13px !important;
  font-weight: 700 !important;
}
#review-pending-page-info > div,
#review-processed-page-info > div,
#review-evidence-page-info > div,
#review-history-page-info > div {
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.04);
  color: var(--body-text-color-subdued);
}
#review-help-panel > div,
#review-claim-detail > div,
#review-record-detail > div,
#review-evidence-detail > div,
#review-result-panel > div,
#review-export-result > div {
  border-left: none !important;
  padding-left: 0 !important;
}
#review-claim-detail,
#review-record-detail,
#review-evidence-detail,
#review-result-panel,
#review-export-result {
  font-size: 14px !important;
}
#search-results-table table th,
#search-results-table table td {
  font-size: 14px !important;
  white-space: pre-wrap !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
  line-height: 1.7 !important;
  vertical-align: top !important;
}
#search-results-table table th:nth-child(1),
#search-results-table table td:nth-child(1) {
  width: 56px !important;
}
#search-results-table table th:nth-child(2),
#search-results-table table td:nth-child(2) {
  width: 156px !important;
}
#search-results-table table th:nth-child(3),
#search-results-table table td:nth-child(3) {
  width: 128px !important;
}
#search-results-table table th:nth-child(4),
#search-results-table table td:nth-child(4) {
  width: 96px !important;
}
#search-results-table table th:nth-child(5),
#search-results-table table td:nth-child(5) {
  width: 96px !important;
}
#search-top-row,
#search-result-row,
#search-export-row {
  gap: 14px !important;
}
#search-help-panel,
#search-result-summary,
#search-result-detail {
  margin-top: 0;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#search-help-panel {
  min-height: 184px !important;
}
#search-help-panel > div,
#search-result-summary > div,
#search-result-detail > div,
#search-export-result > div {
  border-left: none;
  padding-left: 0;
}
#search-action-panel {
  margin-top: 8px !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#search-action-panel > div {
  width: 100%;
}
#search-result-row > .gradio-column {
  min-width: 0 !important;
}
#search-result-row {
  margin-top: 10px !important;
}
#search-results-table,
#search-results-table > div,
#search-results-table > div > div {
  max-width: 100% !important;
}
#search-results-table table {
  width: 100% !important;
  table-layout: fixed !important;
}
#search-results-table button[aria-label="Select column"],
#search-results-table button[aria-label="Select row"] {
  display: none !important;
}
#search-results-table .search-result-cell-selected {
  display: block;
  margin: -8px -10px;
  padding: 8px 10px;
  background: rgba(68, 68, 68, 0.22) !important;
  border-top: 1px solid rgba(68, 68, 68, 0.45);
  border-bottom: 1px solid rgba(68, 68, 68, 0.45);
  font-weight: 600;
}
#search-results-table .search-result-cell-selected-first {
  border-left: 5px solid rgba(68, 68, 68, 0.72);
  padding-left: 12px;
}
#search-results-table tr:has(td:focus-within) td,
#search-results-table tr:has(button:focus) td,
#search-results-table tr:has(.selected) td,
#search-results-table td.selected {
  background: rgba(127, 127, 127, 0.14) !important;
}
#search-results-table tr:has(td:focus-within) td:first-child,
#search-results-table tr:has(button:focus) td:first-child,
#search-results-table tr:has(.selected) td:first-child {
  box-shadow: inset 3px 0 0 0 rgba(127, 127, 127, 0.45) !important;
}
#search-results-table mark,
#search-results-table table th {
  font-size: 12px !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgba(148, 163, 184, 0.06) !important;
}
#search-results-table table tbody tr:hover td {
  background: rgba(148, 163, 184, 0.06) !important;
}
#search-top-row .gradio-dropdown > div,
#search-top-row textarea,
#search-top-row input {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background: rgba(148, 163, 184, 0.04) !important;
}
#search-top-row textarea:focus,
#search-top-row input:focus {
  border-color: rgba(59, 130, 246, 0.42) !important;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.10) !important;
}
#search-page-info > div {
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.04);
  color: var(--body-text-color-subdued);
}
#search-export-row {
  justify-content: flex-start !important;
  padding: 6px 2px 0 2px !important;
  margin: 0 !important;
}
#search-export-result {
  margin-top: 8px !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#search-result-detail mark {
  background: rgba(245, 158, 11, 0.20);
  color: #b45309;
  font-weight: 700;
  padding: 0 3px;
  border-radius: 4px;
  border: 1px solid rgba(245, 158, 11, 0.32);
}
#search-result-detail,
#search-result-summary {
  font-size: 14px !important;
}
#search-results-table {
  min-height: 320px;
}
#search-result-detail {
  min-height: 220px;
}
#search-export-result,
#search-export-result * {
  max-width: 100% !important;
  box-sizing: border-box !important;
  word-break: break-word !important;
  overflow-wrap: anywhere !important;
}
#settings-top-row {
  align-items: stretch !important;
  gap: 12px !important;
}
#settings-main-row,
#settings-knowledge-base-row {
  align-items: flex-start !important;
  gap: 12px !important;
}
#settings-top-row > .gradio-column,
#settings-main-row > .gradio-column,
#settings-knowledge-base-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#settings-main-row > .gradio-column,
#settings-knowledge-base-row > .gradio-column {
  align-self: flex-start !important;
}
#settings-knowledge-base-panel {
  margin-top: 10px;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#settings-footer-panel {
  margin-top: 10px;
  padding: 10px 12px 14px 12px !important;
  box-sizing: border-box !important;
}
#settings-footer-panel > div {
  width: 100%;
  box-sizing: border-box !important;
}
#settings-workspace-panel,
#settings-knowledge-base-panel {
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
#settings-template-list-panel,
#settings-knowledge-base-list-panel {
  margin-top: 0;
  padding: 14px 16px 16px !important;
}
#settings-help-panel,
#settings-runtime-panel,
#settings-template-list-panel,
#settings-template-detail,
#settings-template-form,
#settings-knowledge-base-list-panel,
#settings-knowledge-base-detail,
#settings-knowledge-base-form,
#settings-result-panel,
#settings-export-result,
#settings-knowledge-base-result {
  margin-top: 0;
  padding: 20px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  border-radius: 22px;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.04), transparent 28%),
    var(--block-background-fill);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04);
}
#settings-main-row,
#settings-knowledge-base-row {
  margin-top: 8px !important;
}
#settings-help-panel > div,
#settings-runtime-panel > div,
#settings-template-list-panel > div,
#settings-template-detail > div,
#settings-template-form > div,
#settings-knowledge-base-list-panel > div,
#settings-knowledge-base-detail > div,
#settings-knowledge-base-form > div,
#settings-result-panel > div,
#settings-export-result > div,
#settings-knowledge-base-result > div {
  height: 100%;
}
#settings-help-panel > div,
#settings-runtime-panel > div,
#settings-template-detail > div,
#settings-knowledge-base-detail > div,
#settings-result-panel > div,
#settings-export-result > div,
#settings-knowledge-base-result > div {
  border-left: none;
  padding-left: 0;
}
#settings-help-panel,
#settings-runtime-panel {
  min-height: 188px;
}
#settings-template-detail,
#settings-knowledge-base-detail {
  min-height: 176px;
}
#settings-template-detail > div > div,
#settings-knowledge-base-detail > div > div {
  border: none !important;
  background: transparent !important;
  border-radius: 0 !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
  min-height: auto !important;
}
#settings-template-detail > div > div > div:first-child > div:last-child,
#settings-knowledge-base-detail > div > div > div:first-child > div:last-child {
  display: none !important;
}
#settings-template-detail > div > div ul,
#settings-knowledge-base-detail > div > div ul {
  margin-top: 10px !important;
}
#settings-template-form,
#settings-knowledge-base-form {
  padding: 18px 20px !important;
}
#settings-template-form .gradio-markdown,
#settings-knowledge-base-form .gradio-markdown {
  margin: 0 !important;
}
#settings-template-form > div > .gradio-markdown:not(:first-child),
#settings-knowledge-base-form > div > .gradio-markdown:not(:first-child) {
  margin-top: 6px !important;
  padding-top: 8px !important;
  border-top: 1px solid rgba(148, 163, 184, 0.14) !important;
}
#settings-template-form .gradio-markdown h3,
#settings-knowledge-base-form .gradio-markdown h3 {
  margin: 0 0 8px 0 !important;
  font-size: 15px !important;
  line-height: 1.35 !important;
}
#settings-template-form > div,
#settings-knowledge-base-form > div {
  gap: 10px !important;
}
#settings-template-form .gradio-row,
#settings-knowledge-base-form .gradio-row {
  gap: 10px !important;
  margin-top: 0 !important;
  margin-bottom: 0 !important;
}
#settings-basic-group,
#settings-policy-group,
#settings-prompt-group,
#settings-knowledge-base-basic-group,
#settings-knowledge-base-status-group {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
}
#settings-basic-group > div,
#settings-policy-group > div,
#settings-prompt-group > div,
#settings-knowledge-base-basic-group > div,
#settings-knowledge-base-status-group > div {
  padding: 0 !important;
  gap: 10px !important;
}
#settings-template-form .gradio-textbox,
#settings-template-form .gradio-number,
#settings-template-form .gradio-dropdown,
#settings-template-form .gradio-checkbox,
#settings-knowledge-base-form .gradio-textbox,
#settings-knowledge-base-form .gradio-number,
#settings-knowledge-base-form .gradio-dropdown,
#settings-knowledge-base-form .gradio-checkbox {
  margin: 0 !important;
}
#settings-template-form .gradio-checkbox,
#settings-knowledge-base-form .gradio-checkbox {
  padding-top: 2px !important;
}
#settings-template-table {
  min-height: 0;
  margin-top: 0 !important;
}
#settings-template-table .label-wrap,
#settings-template-table > label,
#settings-knowledge-base-table .label-wrap,
#settings-knowledge-base-table > label {
  display: none !important;
}
#settings-template-table > div,
#settings-template-table > div > div,
#settings-template-table > div > div > div {
  min-height: 0 !important;
}
#settings-template-table .table-wrap {
  margin-top: 0 !important;
}
#settings-template-table button[aria-label="Copy table data"],
#settings-template-table button[aria-label="Fullscreen"] {
  display: none !important;
}
#settings-knowledge-base-table {
  gap: 6px !important;
  min-height: 72px;
}
#settings-template-list-header,
#settings-knowledge-base-list-header {
  margin-bottom: 8px !important;
}
#settings-template-list-header > div,
#settings-knowledge-base-list-header > div {
  padding: 0 !important;
}
.settings-list-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.settings-list-header__title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--body-text-color);
}
.settings-list-header__desc {
  margin: 4px 0 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--body-text-color-subdued);
}
#settings-result-panel,
#settings-export-result,
#settings-knowledge-base-result {
  min-height: 84px;
}
#settings-footer-module {
  padding: 18px 20px !important;
  border: 1px solid rgba(148, 163, 184, 0.12) !important;
  border-radius: 22px !important;
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.04), transparent 28%),
    var(--block-background-fill) !important;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.04) !important;
}
#settings-footer-module > div {
  width: 100%;
}
#settings-footer-module #settings-result-panel,
#settings-footer-module #settings-export-result {
  min-height: auto !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#settings-footer-module #settings-result-panel > div,
#settings-footer-module #settings-export-result > div {
  height: auto !important;
  border-left: none !important;
  padding-left: 0 !important;
}
#settings-export-panel {
  margin-top: 10px !important;
  padding: 10px 0 0 0 !important;
  border-top: 1px solid rgba(148, 163, 184, 0.14) !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-sizing: border-box !important;
}
#settings-export-panel > div {
  width: 100%;
}
#settings-template-page-info,
#settings-knowledge-base-page-info {
  margin-top: 2px !important;
}
#settings-pagination-row,
#settings-list-actions,
#settings-form-actions,
#settings-knowledge-base-pagination-row,
#settings-knowledge-base-list-actions,
#settings-knowledge-base-actions {
  gap: 12px !important;
  flex-wrap: wrap !important;
  margin-top: 8px !important;
}
#settings-list-actions > *,
#settings-form-actions > *,
#settings-knowledge-base-list-actions > *,
#settings-knowledge-base-actions > * {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#settings-list-actions,
#settings-form-actions,
#settings-knowledge-base-list-actions,
#settings-knowledge-base-actions,
#settings-export-row {
  padding: 8px 4px !important;
  margin-top: 6px !important;
  justify-content: flex-start !important;
}
#settings-form-actions,
#settings-knowledge-base-actions {
  justify-content: flex-end !important;
  gap: 12px !important;
  padding: 12px 4px 8px 4px !important;
  margin-top: 12px !important;
  border-top: 1px solid rgba(148, 163, 184, 0.14) !important;
}
#settings-form-actions > *,
#settings-knowledge-base-actions > * {
  flex: 0 0 auto !important;
}
#settings-template-form .gradio-checkbox label,
#settings-knowledge-base-form .gradio-checkbox label {
  font-size: 13px !important;
  line-height: 1.4 !important;
}
#settings-template-page-info > div,
#settings-knowledge-base-page-info > div {
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.04);
  color: var(--body-text-color-subdued);
}
#settings-main-row .gradio-dropdown > div,
#settings-main-row textarea,
#settings-main-row input,
#settings-knowledge-base-row .gradio-dropdown > div,
#settings-knowledge-base-row textarea,
#settings-knowledge-base-row input {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.24) !important;
  background: rgba(148, 163, 184, 0.04) !important;
}
#settings-main-row label,
#settings-knowledge-base-row label {
  font-size: 13px !important;
  font-weight: 700 !important;
}
#settings-export-row {
  justify-content: flex-start !important;
  margin-top: 0 !important;
}
#settings-export-result {
  margin-top: 10px !important;
  padding: 0 !important;
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
}
#search-results-table .label-wrap,
#quality-evidence-table .label-wrap,
#quality-recent-table .label-wrap,
#quality-evaluation-table .label-wrap,
#review-pending-table .label-wrap,
#review-processed-table .label-wrap,
#review-evidence-table .label-wrap,
#review-history-table .label-wrap,
#database-summary-table .label-wrap,
#document-table .label-wrap,
#document-quality-sections-table .label-wrap,
#document-quality-chunks-table .label-wrap,
#document-quality-search-results .label-wrap,
#document-quality-batch-table .label-wrap {
  padding: 0 0 2px 0 !important;
  margin: 0 !important;
  min-height: auto !important;
  font-size: 15px !important;
  font-weight: 700 !important;
  line-height: 1.35 !important;
}
#search-results-table > div,
#quality-evidence-table > div,
#quality-recent-table > div,
#quality-evaluation-table > div,
#review-pending-table > div,
#review-processed-table > div,
#review-evidence-table > div,
#review-history-table > div,
#database-summary-table > div,
#document-table > div,
#document-quality-sections-table > div,
#document-quality-chunks-table > div,
#document-quality-search-results > div,
#document-quality-batch-table > div {
  gap: 0 !important;
}
#search-results-table .table-wrap,
#quality-evidence-table .table-wrap,
#quality-recent-table .table-wrap,
#quality-evaluation-table .table-wrap,
#review-pending-table .table-wrap,
#review-processed-table .table-wrap,
#review-evidence-table .table-wrap,
#review-history-table .table-wrap,
#database-summary-table .table-wrap,
#document-table .table-wrap,
#document-quality-sections-table .table-wrap,
#document-quality-chunks-table .table-wrap,
#document-quality-search-results .table-wrap,
#document-quality-batch-table .table-wrap {
  margin-top: 0 !important;
  padding-top: 0 !important;
}
#search-results-table button[aria-label="Copy table data"],
#search-results-table button[aria-label="Fullscreen"],
#quality-evidence-table button[aria-label="Copy table data"],
#quality-evidence-table button[aria-label="Fullscreen"],
#quality-recent-table button[aria-label="Copy table data"],
#quality-recent-table button[aria-label="Fullscreen"],
#quality-evaluation-table button[aria-label="Copy table data"],
#quality-evaluation-table button[aria-label="Fullscreen"],
#review-pending-table button[aria-label="Copy table data"],
#review-pending-table button[aria-label="Fullscreen"],
#review-processed-table button[aria-label="Copy table data"],
#review-processed-table button[aria-label="Fullscreen"],
#review-evidence-table button[aria-label="Copy table data"],
#review-evidence-table button[aria-label="Fullscreen"],
#review-history-table button[aria-label="Copy table data"],
#review-history-table button[aria-label="Fullscreen"],
#database-summary-table button[aria-label="Copy table data"],
#database-summary-table button[aria-label="Fullscreen"],
#document-table button[aria-label="Copy table data"],
#document-table button[aria-label="Fullscreen"],
#document-quality-sections-table button[aria-label="Copy table data"],
#document-quality-sections-table button[aria-label="Fullscreen"],
#document-quality-chunks-table button[aria-label="Copy table data"],
#document-quality-chunks-table button[aria-label="Fullscreen"],
#document-quality-search-results button[aria-label="Copy table data"],
#document-quality-search-results button[aria-label="Fullscreen"],
#document-quality-batch-table button[aria-label="Copy table data"],
#document-quality-batch-table button[aria-label="Fullscreen"] {
  display: none !important;
}
#quality-dummy-row-1,
#quality-dummy-row-2,
#quality-dummy-row-3,
#quality-dummy-row-4,
#quality-dummy-bottom-row {
  align-items: stretch !important;
  gap: 14px !important;
  margin-top: 8px !important;
}
#quality-dummy-row-1 > .gradio-column,
#quality-dummy-row-2 > .gradio-column,
#quality-dummy-row-3 > .gradio-column,
#quality-dummy-row-4 > .gradio-column,
#quality-dummy-bottom-row > .gradio-column {
  align-self: stretch !important;
  min-width: 0 !important;
}
#quality-dummy-intake-panel,
#quality-dummy-help-panel,
#quality-dummy-template-panel,
#quality-dummy-progress-panel,
#quality-dummy-result-panel,
#quality-dummy-status-panel,
#quality-dummy-claim-list-panel,
#quality-dummy-focus-panel,
#quality-dummy-evidence-panel,
#quality-dummy-evidence-detail,
#quality-dummy-history-panel,
#quality-dummy-action-panel,
#quality-dummy-evaluation-panel,
#quality-dummy-detail-help {
  margin-top: 0;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 22px;
  background: var(--block-background-fill);
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.06);
}
#quality-dummy-template-panel,
#quality-dummy-relation-note,
#quality-dummy-status-panel,
#quality-dummy-focus-panel,
#quality-dummy-evidence-detail,
#quality-dummy-action-panel,
#quality-dummy-detail-help,
#quality-dummy-evidence-panel,
#quality-dummy-history-panel,
#quality-dummy-help-panel,
#quality-dummy-progress-panel,
#quality-dummy-result-panel,
#quality-dummy-evaluation-panel {
  height: 100%;
}
.quality-dummy-note {
  margin: 6px 0 0 0;
  padding: 12px 14px;
  border: 1px dashed rgba(148, 163, 184, 0.26);
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--body-text-color-subdued);
  background: rgba(148, 163, 184, 0.04);
}
.quality-dummy-shell {
  height: 100%;
  padding: 4px 2px;
}
.quality-dummy-shell--primary {
  border-left: 4px solid rgba(59, 130, 246, 0.78);
  padding-left: 14px;
}
.quality-dummy-shell--success {
  border-left: 4px solid rgba(34, 197, 94, 0.78);
  padding-left: 14px;
}
.quality-dummy-shell--warning {
  border-left: 4px solid rgba(245, 158, 11, 0.78);
  padding-left: 14px;
}
.quality-dummy-shell--default {
  border-left: 4px solid rgba(148, 163, 184, 0.42);
  padding-left: 14px;
}
.quality-dummy-kicker {
  margin: 0 0 10px 0;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--body-text-color-subdued);
}
.quality-dummy-title {
  margin: 0 0 14px 0;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--body-text-color);
}
.quality-dummy-subtitle {
  margin: 0 0 14px 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--body-text-color-subdued);
}
.quality-dummy-stat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 14px 0;
}
.quality-dummy-stat {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  background: rgba(148, 163, 184, 0.06);
}
.quality-dummy-stat-label {
  margin: 0 0 4px 0;
  font-size: 12px;
  color: var(--body-text-color-subdued);
}
.quality-dummy-stat-value {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--body-text-color);
}
.quality-dummy-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 14px 0;
}
.quality-dummy-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}
.quality-dummy-chip--danger {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}
.quality-dummy-chip--warning {
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
}
.quality-dummy-chip--primary {
  background: rgba(59, 130, 246, 0.12);
  color: #1d4ed8;
}
.quality-dummy-section {
  margin: 0 0 14px 0;
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 16px;
  background: rgba(148, 163, 184, 0.05);
}
.quality-dummy-section-title {
  margin: 0 0 8px 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--body-text-color);
}
.quality-dummy-section-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.75;
  color: var(--body-text-color-subdued);
}
.quality-dummy-list {
  margin: 0;
  padding-left: 18px;
  font-size: 14px;
  line-height: 1.75;
  color: var(--body-text-color-subdued);
}
.quality-dummy-highlight {
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.14);
}
.quality-dummy-highlight strong {
  color: var(--body-text-color);
}
#quality-dummy-action-panel .gradio-row,
#quality-dummy-intake-panel .gradio-row {
  gap: 10px !important;
}

/* 登录页面：仅在可见时参与布局，避免 visible=False 后仍占满一屏 */
#auth-page.hide,
#auth-page.hidden,
#auth-page[style*="display: none"] {
  display: none !important;
  min-height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
}
#auth-page:not(.hide):not(.hidden):not([style*="display: none"]) {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, var(--background-fill-primary, #f5f7fa) 0%, var(--background-fill-secondary, #c3cfe2) 100%);
}
#auth-center-container {
  max-width: 420px;
  width: 100%;
  margin: 0 auto;
  padding: 0 12px;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  min-height: 0 !important;
  height: auto !important;
  flex: 0 0 auto !important;
}
#auth-center-container h1 {
  text-align: center;
  margin-bottom: 20px;
}
#auth-login-form,
#auth-register-form {
  background: var(--block-background-fill, white);
  border-radius: 14px;
  padding: 22px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
}
#auth-login-form h3,
#auth-register-form h3 {
  text-align: center;
  margin-bottom: 16px;
}
#auth-login-form > div:last-child,
#auth-register-form > div:last-child {
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  gap: 12px !important;
  width: 100% !important;
}
#auth-login-form > div:last-child button.ui-button,
#auth-register-form > div:last-child button.ui-button {
  align-self: center !important;
}

/* 用户信息区：挂到独立绝对定位容器中，确保与标签栏同高同线 */
#main-content {
  position: relative;
}
#main-tabs {
  position: relative;
}
#main-tabs [role="tablist"] {
  align-items: stretch !important;
  min-height: 52px !important;
  padding-right: 320px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}
#main-tabs [role="tablist"] button,
#main-tabs button[role="tab"] {
  min-height: 52px !important;
  height: 52px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
  display: inline-flex !important;
  align-items: center !important;
}
#auth-header-actions {
  position: absolute !important;
  top: -8px !important;
  right: 0 !important;
  z-index: 35 !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: flex-end !important;
  gap: 18px !important;
  width: auto !important;
  min-height: 52px !important;
  height: 52px !important;
  margin: 0 !important;
  padding: 0 !important;
}
#auth-header-actions > .gradio-html,
#auth-header-actions > .gradio-button,
#auth-header-actions > div {
  flex: 0 0 auto !important;
  min-width: 0 !important;
}
#auth-user-display {
  position: static !important;
  width: auto !important;
  max-width: 180px !important;
  flex: 0 0 auto !important;
  font-size: 15px;
  color: var(--body-text-color, #333);
  line-height: 1;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 52px;
  height: 52px;
  padding: 0;
  border-radius: 0;
  background: transparent;
  margin: 0 !important;
  overflow: hidden !important;
  text-overflow: ellipsis !important;
}
#auth-user-display > div,
#auth-user-display p,
#auth-user-display span {
  margin: 0 !important;
}
#auth-user-display span {
  font-size: 15px;
  font-weight: 600;
}
#auth-logout-btn {
  position: static !important;
  width: auto !important;
  min-width: 0 !important;
  flex: 0 0 auto !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  font-size: 14px !important;
  font-weight: 400 !important;
}
#auth-logout-btn > div,
#auth-logout-btn > .wrap,
#auth-logout-btn .wrap,
#auth-logout-btn .gradio-button {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  font-size: 14px !important;
  font-weight: 400 !important;
}
#auth-header-actions #auth-logout-btn button,
#auth-header-actions #auth-logout-btn .gradio-button,
#auth-header-actions #auth-logout-btn button.secondary,
#auth-header-actions #auth-logout-btn .gradio-button.secondary,
#auth-header-actions #auth-logout-btn .wrap button,
body #auth-logout-btn button {
  margin: 0 !important;
  padding: 0 !important;
  font-size: 14px !important;
  font-weight: 400 !important;
  line-height: 1 !important;
  min-height: 52px !important;
  height: 52px !important;
  min-width: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  color: var(--body-text-color, #333) !important;
  border-radius: 0 !important;
  transform: none !important;
  transition: color 0.18s ease !important;
}
#auth-header-actions #auth-logout-btn button:hover,
#auth-header-actions #auth-logout-btn .gradio-button:hover,
#auth-header-actions #auth-logout-btn button:focus,
#auth-header-actions #auth-logout-btn .gradio-button:focus {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  transform: none !important;
  color: rgba(37, 99, 235, 0.92) !important;
  font-size: 14px !important;
  font-weight: 400 !important;
}
#auth-header-actions #auth-logout-btn button:focus-visible,
#auth-header-actions #auth-logout-btn .gradio-button:focus-visible,
#auth-header-actions #auth-logout-btn button:active,
#auth-header-actions #auth-logout-btn .gradio-button:active {
  outline: none !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  transform: none !important;
  font-size: 14px !important;
  font-weight: 400 !important;
}
@media (max-width: 960px) {
  #main-tabs [role="tablist"] {
    padding-right: 0 !important;
    min-height: 88px !important;
  }
  #auth-header-actions {
    top: 48px !important;
    min-height: 36px !important;
    height: 36px !important;
    gap: 14px !important;
  }
  #auth-user-display {
    min-height: 36px !important;
    height: 36px !important;
  }
  #auth-logout-btn button,
  #auth-logout-btn .gradio-button {
    min-height: 36px !important;
    height: 36px !important;
  }
}
"""
