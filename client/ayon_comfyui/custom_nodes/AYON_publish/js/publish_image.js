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
            
            // Override onConfigure to initialize the path when the node is loaded
            nodeType.prototype.onConfigure = function(info) {
                const result = onConfigure ? onConfigure.call(this, info) : undefined;
                
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
                
                this.setSize([350, 200]);
                this.title = "AYON Publish";
                
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
                
                // Make output_path widget read-only but ensure it's visible
                for (const w of this.widgets) {
                    if (w.name === "output_path") {
                        // Don't disable it completely as that might affect display
                        w.disabled = false;
                        w.readonly = true; // Use readonly instead if supported
                        
                        // Adjust height but don't make it too small
                        if (w.options) {
                            w.options.height = 40; // Reasonable height to see the path
                        } else {
                            w.options = { height: 40 };
                        }
                        
                        // If the widget has a DOM element, make it read-only
                        if (w.inputEl) {
                            w.inputEl.readOnly = true;
                            w.inputEl.style.backgroundColor = "#2a2a2a"; // Dark gray background
                            w.inputEl.style.color = "#e0e0e0"; // Light text for contrast
                            w.inputEl.style.border = "1px solid #444"; // Subtle border
                        }
                    }
                }
                
                // Schedule path update after node is fully created
                setTimeout(() => {
                    console.log("Initializing output path after node creation");
                    this.updateOutputPath();
                }, 100);
                
                console.log("PublishImage node created with size:", this.size);
                return result;
            };
            
            // Add direct widget change handlers
            const origComputeSize = nodeType.prototype.computeSize;
            nodeType.prototype.computeSize = function(size) {
                const result = origComputeSize ? origComputeSize.call(this, size) : size;
                
                if (result[0] < 350) result[0] = 350;
                if (result[1] < 200) result[1] = 200;
                
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
