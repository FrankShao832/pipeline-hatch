from PySide6.QtWidgets import (
    QDialog, QPushButton, QHBoxLayout, QLabel, QVBoxLayout, QFileDialog
)


class SettingsPanel(QDialog):
    def __init__(self):
        super(SettingsPanel, self).__init__()

        ok_btn = QPushButton('OK', self)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel', self)
        cancel_btn.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)

        self.root_path_label = QLabel('Projects Root: ')
        self.root_path_value = QLabel('None')
        self.label_layout = QHBoxLayout()
        self.label_layout.addWidget(self.root_path_label)
        self.label_layout.addWidget(self.root_path_value)
        self.root_btn = QPushButton('Set Project Root Directory')

        self.publish_root_label = QLabel('Publish Root: ')
        self.publish_root_value = QLabel('None')
        self.publish_label_layout = QHBoxLayout()
        self.publish_label_layout.addWidget(self.publish_root_label)
        self.publish_label_layout.addWidget(self.publish_root_value)
        self.publish_root_btn = QPushButton('Set Publish Root Directory')

        self.main_layout = QVBoxLayout()
        self.main_layout.addLayout(self.label_layout)
        self.main_layout.addWidget(self.root_btn)
        self.main_layout.addLayout(self.publish_label_layout)
        self.main_layout.addWidget(self.publish_root_btn)
        self.main_layout.addLayout(btn_layout)

        self.setLayout(self.main_layout)

        self.connections()

    def connections(self):

        self.root_btn.clicked.connect(self.set_root_path)
        self.publish_root_btn.clicked.connect(self.set_publish_root_path)

    def set_root_path(self):

        root_path = QFileDialog.getExistingDirectory()

        if root_path:
            self.root_path_value.setText(f'{root_path}')

        return root_path

    def set_publish_root_path(self):

        publish_root_path = QFileDialog.getExistingDirectory()

        if publish_root_path:
            self.publish_root_value.setText(f'{publish_root_path}')

        return publish_root_path
