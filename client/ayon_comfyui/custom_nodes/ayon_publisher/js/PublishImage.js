import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "PublishImage.PublishImage",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "AYON Publish") {
            console.log("Registering PublishImage node");

            // Store original methods
            const getMenuOptions = nodeType.prototype.getMenuOptions;
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            const onDrawBackground = nodeType.prototype.onDrawBackground;
            const onConfigure = nodeType.prototype.onConfigure;

            // Define the publish function
            async function publishImage(node) {
                try {
                    console.log("Publishing image from node", node.id);
                    const response = await fetch('/publish_image', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            node_id: node.id,
                            workflow: app.graph.serialize()
                        })
                    });

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const result = await response.json();

                    if (result.success) {
                        alert("Image published successfully!\nOutput: " + result.output);
                    } else {
                        alert("Error: " + (result.error || "Unknown error occurred"));
                    }
                } catch (error) {
                    console.error("Failed to publish image:", error);
                    alert("Failed to publish image: " + error.message);
                }
            }

            function formatFileList(files){
                if (!files || files.length === 0) {
                    return "No files selected";
                }

                // Format the file list with numbers and just the filenames
                return files.map((path, index) => {
                    const filename = path.split(/[\/\\]/).pop(); // Get just the filename
                    return `${index + 1}. ${filename}`;
                }).join("\n");
            }

            // Define the select files function
            async function selectFiles(node, appendMode = false) {
                try {
                    console.log(`Opening file selector from node ${node.id}, append mode: ${appendMode}`);

                    // Get current files if in append mode
                    let currentFiles = [];
                    if (appendMode && node.properties && node.properties.selectedFiles) {
                        currentFiles = node.properties.selectedFiles;
                    }

                    // Disable buttons during selection to prevent multiple clicks
                    for (const w of node.widgets) {
                        if (w.name === "Select Files" || w.name === "Append Files") {
                            if (w.inputEl) {
                                w.inputEl.disabled = true;
                                w.inputEl.style.opacity = "0.5";
                                w.inputEl.style.cursor = "wait";
                            }
                        }
                    }

                    const response = await fetch('/selected_files', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            node_id: node.id,
                            workflow: app.graph.serialize(),
                            append_mode: appendMode,
                            current_files: currentFiles
                        })
                    });

                    // Re-enable buttons after selection
                    for (const w of node.widgets) {
                        if (w.name === "Select Files" || w.name === "Append Files") {
                            if (w.inputEl) {
                                w.inputEl.disabled = false;
                                w.inputEl.style.opacity = "1";
                                w.inputEl.style.cursor = "pointer";
                            }
                        }
                    }

                    if (!response.ok) {
                        const errorText = await response.text();
                        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
                    }

                    const result = await response.json();

                    if (result.success) {
                        // Store the full paths in a hidden widget
                        for (const w of node.widgets) {
                            if (w.name === "full_paths") {
                                w.value = result.files.join("\n");
                            }

                            // Update the combo widget with file names
                            if (w.name === "selected_files") {
                                if (result.files.length === 0) {
                                    w.options.values = ["No files selected"];
                                    w.value = "No files selected";
                                } else {
                                    // Extract just the filenames for display
                                    const fileNames = result.files.map(path => path.split(/[\/\\]/).pop());
                                    w.options.values = fileNames;
                                    w.value = fileNames[0]; // Select the first file
                                }

                                // Update the DOM element if it exists
                                if (w.inputEl) {
                                    // For combo widgets, we need to rebuild the options
                                    if (w.inputEl.tagName === "SELECT") {
                                        w.inputEl.innerHTML = "";
                                        w.options.values.forEach(value => {
                                            const option = document.createElement("option");
                                            option.value = value;
                                            option.text = value;
                                            w.inputEl.add(option);
                                        });
                                        w.inputEl.value = w.value;
                                    } else {
                                        w.inputEl.value = w.value;
                                    }
                                }

                                // Trigger any change events
                                if (w.callback) {
                                    w.callback(w.value);
                                }
                            }

                            // Update the file count display
                            if (w.name === "file_count") {
                                w.value = `${result.files.length} file(s) selected`;
                                if (w.inputEl) {
                                    w.inputEl.value = w.value;
                                }
                            }
                        }

                        // Store the files in the node for later use
                        node.properties = node.properties || {};
                        node.properties.selectedFiles = result.files;

                        // Force a redraw of the node
                        node.setDirtyCanvas(true, true);

                        console.log("Files selected:", result.files);
                    } else {
                        alert("Error: " + (result.error || "Unknown error occurred"));
                    }
                } catch (error) {
                    console.error("Failed to select files:", error);
                    alert("Failed to select files: " + error.message);

                    // Make sure buttons are re-enabled in case of error
                    for (const w of node.widgets) {
                        if (w.name === "Select Files" || w.name === "Append Files") {
                            if (w.inputEl) {
                                w.inputEl.disabled = false;
                                w.inputEl.style.opacity = "1";
                                w.inputEl.style.cursor = "pointer";
                            }
                        }
                    }
                }
            }

            nodeType.prototype.onConfigure = function(info) {
                const result = onConfigure ? onConfigure.call(this, info) : undefined;

                // Restore selected files from properties if available
                if (info.properties && info.properties.selectedFiles) {
                    const files = info.properties.selectedFiles;

                    // Update the widgets with the restored files
                    for (const w of this.widgets) {
                        if (w.name === "full_paths") {
                            w.value = files.join("\n");
                        }
                        if (w.name === "selected_files") {
                            if (files.length === 0) {
                                w.options.values = ["No files selected"];
                                w.value = "No files selected";
                            } else {
                                // Create array of filenames for the dropdown
                                const fileOptions = files.map(path => {
                                    return path.split(/[\/\\]/).pop(); // Get just the filename
                                });

                                // Update the combobox options
                                w.options.values = fileOptions;
                                w.value = fileOptions[0]; // Select the first file by default

                                // Update the DOM element
                                if (w.inputEl) {
                                    // This will rebuild the options in the select element
                                    w.inputEl.innerHTML = "";
                                    for (const option of w.options.values) {
                                        const optionEl = document.createElement("option");
                                        optionEl.value = option;
                                        optionEl.innerText = option;
                                        w.inputEl.appendChild(optionEl);
                                    }
                                    w.inputEl.value = w.value;
                                }
                            }
                        }
                        if (w.name === "file_count") {
                            w.value = `${files.length} file(s) selected`;
                            if (w.inputEl) {
                                w.inputEl.value = w.value;
                            }
                        }
                    }
                }

                // Schedule path update after node is fully configured
                setTimeout(() => {
                    if (this.updateOutputPath) {
                        console.log("Initializing output path after node configuration");
                        this.updateOutputPath();
                    }

                    // Make output_path widget read-only
                    for (const w of this.widgets) {
                        if (w.name === "output_path") {
                            w.disabled = false;
                            w.readonly = true;
                            if (w.options) {
                                w.options.height = 40;
                            } else {
                                w.options = { height: 40 };
                            }

                            // Apply styling to make it more readable
                            if (w.inputEl) {
                                w.inputEl.readOnly = true;
                                w.inputEl.style.backgroundColor = "#2a2a2a"; // Dark gray background
                                w.inputEl.style.color = "#e0e0e0"; // Light text for contrast
                                w.inputEl.style.border = "1px solid #444"; // Subtle border
                            }
                        }
                    }
                }, 100);

                return result;
            };

            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                // Set size and title - using the larger size to accommodate all widgets
                this.setSize([350, 280]);
                this.title = "AYON Publish";

                // Add file selector widgets
                // Add a hidden widget to store the full paths
                this.addWidget("text", "full_paths", "", null, {
                    hidden: true
                });

                // Add a file count display
                this.addWidget("text", "file_count", "0 file(s) selected", null, {
                    readonly: true
                });

                // Add a text widget to display selected files
                const filesWidget = this.addWidget("combo", "selected_files", "No files selected", null, {
                    values: ["No files selected"]
                });

                // Add a custom styled Select Files button (new selection)
                const selectButton = this.addWidget("button", "Select Files", "Select Files", () => {
                    selectFiles(this, false);
                });

                // Add a custom styled Append Files button
                const appendButton = this.addWidget("button", "Append Files", "Append Files", () => {
                    selectFiles(this, true);
                });

                // Initialize properties to store selected files
                this.properties = this.properties || {};
                this.properties.selectedFiles = [];

                // Add a method to update the output path
                this.updateOutputPath = function() {
                    // Find the necessary widgets
                    let folderPathWidget = null;
                    let taskNameWidget = null;
                    let outputPathWidget = null;
                    let variantWidget = null;
                    let productTypeWidget = null;

                    for (const w of this.widgets) {
                        if (w.name === "folder_path") folderPathWidget = w;
                        else if (w.name === "task_name") taskNameWidget = w;
                        else if (w.name === "output_path") outputPathWidget = w;
                        else if (w.name === "variant") variantWidget = w;
                        else if (w.name === "product_type") productTypeWidget = w;
                    }

                    if (folderPathWidget && taskNameWidget && outputPathWidget && variantWidget && productTypeWidget) {
                        console.log("Updating output path...");
                        // Call API to get updated path
                        fetch('/update_output_path', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                folder_path: folderPathWidget.value,
                                task_name: taskNameWidget.value,
                                variant: variantWidget.value,
                                product_type: productTypeWidget.value
                            })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success && data.output_path) {
                                console.log("Received new path:", data.output_path);
                                // Directly set the value property
                                outputPathWidget.value = data.output_path;
                                // Also update the DOM element if it exists
                                if (outputPathWidget.inputEl) {
                                    outputPathWidget.inputEl.value = data.output_path;
                                    outputPathWidget.inputEl.readOnly = true;
                                    outputPathWidget.inputEl.style.backgroundColor = "#2a2a2a"; // Dark gray background
                                    outputPathWidget.inputEl.style.color = "#e0e0e0"; // Light text for contrast
                                    outputPathWidget.inputEl.style.border = "1px solid #444"; // Subtle border
                                }
                                // Make sure the widget is not disabled for the update
                                const wasDisabled = outputPathWidget.disabled;
                                outputPathWidget.disabled = false;
                                // Trigger any change events
                                if (outputPathWidget.callback) {
                                    outputPathWidget.callback(data.output_path);
                                }
                                // Restore disabled state
                                outputPathWidget.disabled = wasDisabled;
                                // Force a redraw of the node
                                this.setDirtyCanvas(true, true);
                            } else {
                                console.error("Failed to get output path:", data.error || "Unknown error");
                            }
                        })
                        .catch(error => {
                            console.error("Failed to update output path:", error);
                        });
                    } else {
                        console.error("Could not find all required widgets");
                    }
                };

                // Add a method to update the task list based on selected folder
                this.updateTasksForFolder = function() {
                    // Find the necessary widgets
                    let folderPathWidget = null;
                    let taskNameWidget = null;

                    for (const w of this.widgets) {
                        if (w.name === "folder_path") folderPathWidget = w;
                        else if (w.name === "task_name") taskNameWidget = w;
                    }

                    if (folderPathWidget && taskNameWidget) {
                        console.log("Updating tasks for folder:", folderPathWidget.value);

                        // Call API to get tasks for this folder
                        fetch('/get_tasks_for_folder', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({
                                folder_path: folderPathWidget.value
                            })
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success && data.tasks && data.tasks.length > 0) {
                                console.log("Received tasks:", data.tasks);

                                // Store current task value
                                const currentTask = taskNameWidget.value;

                                // Update the task_name widget options
                                taskNameWidget.options = taskNameWidget.options || {};
                                taskNameWidget.options.values = data.tasks;

                                // If the current task is not in the list, set it to the first task
                                if (!data.tasks.includes(currentTask)) {
                                    taskNameWidget.value = data.tasks[0];
                                }

                                // Update the output path after changing the task
                                this.updateOutputPath();

                                // Force widget to redraw
                                this.setDirtyCanvas(true, false);
                            } else {
                                console.error("Failed to get tasks:", data.error || "Unknown error");
                            }
                        })
                        .catch(error => {
                            console.error("Failed to update tasks:", error);
                        });
                    } else {
                        console.error("Could not find folder_path or task_name widgets");
                    }
                };

                // Add a custom styled Publish button
                const publishButton = this.addWidget("button", "Publish", null, () => {
                    publishImage(this);
                });

                if (publishButton) {
                    publishButton.options = publishButton.options || {};
                    publishButton.options.backgroundColor = "rgba(0, 0, 0, 0.6)";
                    publishButton.options.textColor = "#00d7a0";
                    publishButton.options.fontWeight = "bold";
                }

                // Schedule DOM manipulation after node is fully created
                setTimeout(() => {
                    // Style the widgets
                    for (const w of this.widgets) {
                        if (w.name === "selected_files" && w.inputEl) {
                            w.inputEl.style.backgroundColor = "#2a2a2a";
                            w.inputEl.style.color = "#e0e0e0";
                            w.inputEl.style.border = "1px solid #444";
                            w.inputEl.style.fontFamily = "monospace";
                            w.inputEl.style.fontSize = "12px";
                            w.inputEl.style.padding = "8px";
                            w.inputEl.style.borderRadius = "4px";
                            w.inputEl.style.width = "100%";
                            w.inputEl.style.boxSizing = "border-box";
                        }

                        if (w.name === "file_count" && w.inputEl) {
                            w.inputEl.readOnly = true;
                            w.inputEl.style.backgroundColor = "transparent";
                            w.inputEl.style.border = "none";
                            w.inputEl.style.color = "#aaa";
                            w.inputEl.style.fontSize = "12px";
                            w.inputEl.style.fontStyle = "italic";
                            w.inputEl.style.textAlign = "right";
                            w.inputEl.style.padding = "4px";
                        }

                        // Style the Select Files button
                        if (w.name === "Select Files" && w.inputEl) {
                            w.inputEl.style.backgroundColor = "#3498db";
                            w.inputEl.style.color = "white";
                            w.inputEl.style.fontWeight = "bold";
                            w.inputEl.style.padding = "8px 12px";
                            w.inputEl.style.border = "none";
                            w.inputEl.style.borderRadius = "4px";
                            w.inputEl.style.cursor = "pointer";
                            w.inputEl.style.margin = "5px 0";
                            w.inputEl.style.display = "block";
                            w.inputEl.style.width = "100%";
                        }

                        // Style the Append Files button
                        if (w.name === "Append Files" && w.inputEl) {
                            w.inputEl.style.backgroundColor = "#27ae60";
                            w.inputEl.style.color = "white";
                            w.inputEl.style.fontWeight = "bold";
                            w.inputEl.style.padding = "8px 12px";
                            w.inputEl.style.border = "none";
                            w.inputEl.style.borderRadius = "4px";
                            w.inputEl.style.cursor = "pointer";
                            w.inputEl.style.margin = "5px 0";
                            w.inputEl.style.display = "block";
                            w.inputEl.style.width = "100%";
                        }

                        // Style for output_path widget if it exists
                        if (w.name === "output_path" && w.inputEl) {
                            w.inputEl.readOnly = true;
                            w.inputEl.style.backgroundColor = "#2a2a2a";
                            w.inputEl.style.color = "#e0e0e0";
                            w.inputEl.style.border = "1px solid #444";
                        }
                    }
                }, 500);

                console.log("Combined node created with size:", this.size);
                return result;
            };

            // Override the widget constructor to add change listeners
            const origCreateWidget = LGraphNode.prototype.addWidget;
            nodeType.prototype.addWidget = function(type, name, value, callback, options) {
                if (name === "output_path") {
                    options = options || {};
                    options.height = 40;
                    const widget = origCreateWidget.call(this, type, name, value, callback, options);
                    widget.disabled = false;
                    widget.readonly = true;
                    // If the widget has a DOM element, style it
                    if (widget.inputEl) {
                        widget.inputEl.readOnly = true;
                        widget.inputEl.style.backgroundColor = "#2a2a2a"; // Dark gray background
                        widget.inputEl.style.color = "#e0e0e0"; // Light text for contrast
                        widget.inputEl.style.border = "1px solid #444"; // Subtle border
                    }
                    return widget;
                }

                const widget = origCreateWidget.call(this, type, name, value, callback, options);

                // Add change listeners for specific widgets
                if (name === "folder_path" && type === "combo") {
                    const node = this;
                    // Store the original callback
                    const origCallback = widget.callback;
                    // Override the callback
                    widget.callback = function(value, event, skipCallback) {
                        // Call the original callback
                        if (origCallback) {
                            origCallback.call(this, value, event, skipCallback);
                        }
                        // Update tasks for this folder
                        console.log(`Folder changed to ${value}`);
                        node.updateTasksForFolder();
                        // Update the output path
                        setTimeout(() => {
                            node.updateOutputPath();
                        }, 100); // Small delay to ensure tasks are updated first
                    };
                }
                else if ((name === "variant" || name === "product_type" || name === "task_name")) {
                    const node = this;
                    // Store the original callback
                    const origCallback = widget.callback;
                    // Override the callback
                    widget.callback = function(value, event, skipCallback) {
                        // Call the original callback
                        if (origCallback) {
                            origCallback.call(this, value, event, skipCallback);
                        }
                        // Update the output path
                        console.log(`Widget ${name} changed to ${value}`);
                        node.updateOutputPath();
                    };
                }

                return widget;
            };

            // Override the computeSize method to ensure minimum size
            const origComputeSize = nodeType.prototype.computeSize;
            nodeType.prototype.computeSize = function(size) {
                const result = origComputeSize ? origComputeSize.call(this, size) : size;

                if (result[0] < 350) result[0] = 350;
                if (result[1] < 280) result[1] = 280; // Increased minimum height for two buttons

                return result;
            };

            // Override the serialize method to save selected files
            const origSerialize = nodeType.prototype.serialize;
            nodeType.prototype.serialize = function() {
                const data = origSerialize ? origSerialize.call(this) : {};

                // Make sure properties are included
                if (this.properties && this.properties.selectedFiles) {
                    data.properties = data.properties || {};
                    data.properties.selectedFiles = this.properties.selectedFiles;
                }

                return data;
            };

            // Override onDrawBackground method
            nodeType.prototype.onDrawBackground = function(ctx) {
                try {
                    // Call original method
                    if (onDrawBackground) {
                        onDrawBackground.apply(this, arguments);
                    }
                } catch (error) {
                    console.error("Error drawing node background:", error);
                }
            };

        }
    }
});
