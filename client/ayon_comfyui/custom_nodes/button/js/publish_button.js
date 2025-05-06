import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "publishButton.publishButton",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "publishButton") {
            const getMenuOptions = nodeType.prototype.getMenuOptions;
            nodeType.prototype.getMenuOptions = function() {
                const options = getMenuOptions ? getMenuOptions.apply(this, arguments) : [];
                
                options.push({
                    content: "Publish",
                    callback: async () => {
                        try {
                            const response = await fetch('/run_custom_code', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({})
                            });
                    
                            if (!response.ok) {
                                throw new Error(`HTTP error! status: ${response.status}`);
                            }
                    
                            const result = await response.json();
                    
                            if (result.success) {
                                alert("Python code executed successfully!\nOutput: " + result.output);
                            } else {
                                alert("Error: " + (result.error || "Unknown error occurred"));
                            }
                        } catch (error) {
                            console.error("Failed to run Python code:", error);
                            alert("Failed to run Python code: " + error.message);
                        }
                    }
                });
                
                return options;
            };
            
            // Draw a message on the node
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function(ctx) {
                if (onDrawForeground) {
                    onDrawForeground.apply(this, arguments);
                }
                
                // Draw instruction text
                ctx.fillStyle = "#00d7a0";
                ctx.font = "12px Arial";
                ctx.textAlign = "center";
                ctx.fillText("Right-click for publish options", this.size[0] / 2, 40);
            };
            
            // Set minimum size
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                this.setSize([220, 80]);
                this.title = "Publish";
                return result;
            };
        }
    }
});
