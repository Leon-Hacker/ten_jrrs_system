# intermittent_dialog.py
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel

class IntermittentOperationDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Intermittent Operation Message")
        self.setGeometry(400, 200, 300, 200)

        # Create layout and label
        layout = QVBoxLayout()
        self.message_label = QLabel("Waiting for updates...", self)
        layout.addWidget(self.message_label)

        self.setLayout(layout)

    def update_message(self, message):
        """Update the displayed message in the dialog."""
        self.message_label.setText(message)
